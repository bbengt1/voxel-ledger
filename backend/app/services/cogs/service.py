"""COGS posting service (Phase 6.3, #95).

Wires the pure :func:`compute_cogs` calculator to the inventory ledger
and the journal-entry posting pipeline. Three public entry points:

* :func:`preview` — read-only ``SaleCogsBreakdown`` used by the
  sale-detail UI to show "this sale will draw down X units at Y cost"
  before the operator clicks Confirm.
* :func:`post_for_sale` — invoked by :func:`app.services.sales.confirm`.
  For each ``kind=product`` line: load oldest-first FIFO lots, run the
  calculator, emit one ``inventory.TransactionRecorded`` per consumed
  lot tagged ``sale_consumption``. For ``kind=job`` lines: cost basis
  is the job's recorded run cost (cost-engine snapshot). For
  ``kind=manual`` lines: cost is zero. Then post ONE
  ``accounting.JournalEntryPosted`` for the whole sale and emit the
  ``sales.SalePosted`` audit event.
* :func:`reverse_for_sale` — invoked by :func:`app.services.sales.cancel`
  when cancelling a previously-confirmed sale. Emits inverse inventory
  transactions (positive quantity restoring lots) + a reversing journal
  entry whose debit/credit pairs are swapped, and emits the
  ``sales.SaleReversed`` audit event.

Atomicity invariant
-------------------
All side effects share the caller's session. ``confirm()`` calls
``post_for_sale()`` inside the same transaction that flipped the sale's
state; if any step (lot load, calculator, inventory transaction insert,
journal entry post, event emission) raises, the outer transaction rolls
back and NOTHING persists — not the state flip, not the inventory rows,
not the journal entry, not the audit events. This is the keystone v2
invariant for the sales pathway. Do not introduce nested commits.

Inventory-credit account
------------------------
The journal entry's inventory-side credit is routed to the dedicated
``sales_posting.default_inventory_account_id`` setting. If unset, the
service raises :class:`MissingSalesPostingAccountError` with the same
"configure default sales-posting accounts" message used for the other
required keys. The earlier shortcut of walking up the chart-of-accounts
to ``cogs_account_id``'s parent was removed because it coupled two
unrelated accounts and broke any chart of accounts that didn't nest
inventory under COGS.

Reversal FK
-----------
``post_for_sale`` writes the new journal entry's ID to
``sale.posting_journal_entry_id`` inside the same transaction; the
column is the durable handle ``reverse_for_sale`` uses to find the
entry to reverse. Description-based scanning of the GL is no longer
used — the only legitimate path from a confirmed sale to its posting
entry is the column FK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import sales as sales_events
from app.models.inventory_transaction import (
    ENTITY_KIND_PRODUCT,
    KIND_SALE_CONSUMPTION,
    InventoryTransaction,
)
from app.models.journal_entry import JournalEntry
from app.models.sale import Sale, SaleItemKind
from app.models.sales_channel import SalesChannel
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import inventory_transactions as inventory_tx_service
from app.services import journal_entries as journal_service
from app.services.cogs.fifo import (
    CogsConsumption,
    InsufficientInventory,
    InventoryLot,
    compute_cogs,
)
from app.services.cost_engine.service import CostEngineService
from app.services.settings.service import SettingsService

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CogsServiceError(Exception):
    """Base class. Routers default to 400."""


class MissingSalesPostingAccountError(CogsServiceError):
    """Required ``sales_posting.*`` setting (or channel default) isn't set.

    Mapped to 400 with a clear "configure default sales-posting
    accounts" message — the operator needs to set the GL account IDs
    via the settings endpoint (or the channel's default account
    columns) before any sale can confirm.
    """


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SaleLineCogs:
    """COGS preview / posting result for one sale line."""

    line_number: int
    kind: str
    product_id: uuid.UUID | None
    job_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    extended_amount: Decimal
    cost: Decimal
    consumption: list[CogsConsumption]


@dataclass(frozen=True)
class SaleCogsBreakdown:
    sale_id: uuid.UUID
    sale_number: str
    state: str
    subtotal: Decimal
    discount_amount: Decimal
    shipping_amount: Decimal
    tax_amount: Decimal
    channel_fee_amount: Decimal
    total_amount: Decimal
    total_cost: Decimal
    lines: list[SaleLineCogs]


@dataclass(frozen=True)
class PostResult:
    """Return value of :func:`post_for_sale` / :func:`reverse_for_sale`."""

    journal_entry_id: uuid.UUID
    inventory_transaction_ids: list[uuid.UUID]
    total_cost: Decimal


# ---------------------------------------------------------------------------
# Lot loading
# ---------------------------------------------------------------------------


async def _load_lots(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    fallback_unit_cost: Decimal | None = None,
) -> list[InventoryLot]:
    """Synthesize FIFO lots for any ``(entity_kind, entity_id)`` from the
    ``inventory_transaction`` ledger.

    Each positive-quantity row is a candidate lot. We drain prior
    negative-quantity rows against the positives oldest-first to compute
    each lot's remaining quantity. Lots with ``remaining <= 0`` are
    skipped.

    ``location_id`` scopes the synthesis to one location (used by builds,
    which consume parts from a specific consumption location). ``None``
    means ledger-wide FIFO (the product-sale path, unchanged).

    ``unit_cost`` comes from ``unit_cost_at_transaction``; when NULL
    (e.g. a ``production_in`` row written before unit costs were
    captured) we fall back to ``fallback_unit_cost`` (the entity's cached
    cost), then to zero so the calculator stays deterministic. Operators
    repair zero-cost lots via an adjustment.
    """
    stmt = (
        select(InventoryTransaction)
        .where(InventoryTransaction.entity_kind == entity_kind)
        .where(InventoryTransaction.entity_id == entity_id)
    )
    if location_id is not None:
        stmt = stmt.where(InventoryTransaction.location_id == location_id)
    stmt = stmt.order_by(asc(InventoryTransaction.occurred_at), asc(InventoryTransaction.id))
    rows = list((await session.execute(stmt)).scalars().all())

    fallback = _q(fallback_unit_cost) if fallback_unit_cost is not None else _ZERO

    positive: list[dict] = []
    negative_magnitude = _ZERO
    for row in rows:
        qty = _q(row.quantity)
        if qty > _ZERO:
            unit_cost = (
                _q(row.unit_cost_at_transaction)
                if row.unit_cost_at_transaction is not None
                else fallback
            )
            positive.append(
                {
                    "lot_id": row.id,
                    "remaining": qty,
                    "unit_cost": unit_cost,
                    "location_id": row.location_id,
                }
            )
        elif qty < _ZERO:
            negative_magnitude = _q(negative_magnitude + (-qty))

    remaining_to_drain = negative_magnitude
    for lot in positive:
        if remaining_to_drain <= _ZERO:
            break
        take = lot["remaining"] if lot["remaining"] < remaining_to_drain else remaining_to_drain
        lot["remaining"] = _q(lot["remaining"] - take)
        remaining_to_drain = _q(remaining_to_drain - take)

    return [
        InventoryLot(
            lot_id=lot["lot_id"],
            remaining_quantity=lot["remaining"],
            unit_cost=lot["unit_cost"],
        )
        for lot in positive
        if lot["remaining"] > _ZERO
    ]


async def _load_product_lots(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
) -> list[InventoryLot]:
    """Ledger-wide FIFO lots for a product (the sale-COGS path)."""
    return await _load_lots(session, entity_kind=ENTITY_KIND_PRODUCT, entity_id=product_id)


async def cost_consumption(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    quantity: Decimal,
    location_id: uuid.UUID,
    fallback_unit_cost: Decimal | None = None,
) -> Decimal:
    """FIFO cost basis for consuming ``quantity`` of an entity at a
    location (assembly-line epic #267 Phase 6a).

    Used by the Build service to value the parts it consumes at their
    actual ledger lot cost rather than a cached snapshot. Location-scoped
    FIFO. Returns the **total** cost across the consumed lots; the caller
    derives an effective unit cost as ``total / quantity``.

    Lots are loaded with ``fallback_unit_cost`` filling in any NULL
    lot costs (decision #3). If the lots can't cover the request the
    underlying calculator raises :class:`InsufficientInventory` — but the
    Build service pre-checks on-hand at the same location, so this is a
    guardrail, not the primary path.
    """
    lots = await _load_lots(
        session,
        entity_kind=entity_kind,
        entity_id=entity_id,
        location_id=location_id,
        fallback_unit_cost=fallback_unit_cost,
    )
    result = compute_cogs(product_id=entity_id, quantity=quantity, lots=lots)
    return result.total_cost


async def _resolve_lot_location_id(session: AsyncSession, *, lot_id: uuid.UUID) -> uuid.UUID:
    stmt = select(InventoryTransaction.location_id).where(InventoryTransaction.id == lot_id)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise CogsServiceError(f"inventory_transaction (lot) {lot_id} not found")
    return row[0]


# ---------------------------------------------------------------------------
# Settings + account resolution
# ---------------------------------------------------------------------------


async def _require_account(session: AsyncSession, *, key: str, why: str) -> uuid.UUID:
    value = await SettingsService.get(key, session=session)
    if value is None:
        raise MissingSalesPostingAccountError(
            f"configure default sales-posting accounts: {key!r} is unset " f"(needed to {why})"
        )
    if not isinstance(value, uuid.UUID):
        value = uuid.UUID(str(value))
    return value


async def _load_sale(session: AsyncSession, sale_id: uuid.UUID) -> Sale:
    stmt = select(Sale).where(Sale.id == sale_id).options(selectinload(Sale.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CogsServiceError(f"sale {sale_id} not found")
    return row


async def _load_channel(session: AsyncSession, channel_id: uuid.UUID) -> SalesChannel:
    stmt = select(SalesChannel).where(SalesChannel.id == channel_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise CogsServiceError(f"sales channel {channel_id} not found")
    return row


# ---------------------------------------------------------------------------
# Line costing
# ---------------------------------------------------------------------------


async def _cost_for_job_line(
    session: AsyncSession, *, job_id: uuid.UUID, quantity: Decimal
) -> Decimal:
    """Cost basis for a ``kind=job`` line is the job's recorded run cost.

    Delegates to :class:`CostEngineService` which assembles the
    snapshot from the plate's recorded materials + per-printer machine
    rates + labor + overhead. The result is per-piece cost times the
    line's quantity.
    """
    result = await CostEngineService.calculate_for_job(job_id, session=session)
    return _q(_q(result.cost_per_piece) * _q(quantity))


# ---------------------------------------------------------------------------
# Public: preview
# ---------------------------------------------------------------------------


async def preview(sale_id: uuid.UUID, *, session: AsyncSession) -> SaleCogsBreakdown:
    """Compute the COGS breakdown for ``sale_id`` without writing anything.

    Safe to call on a draft sale; the FIFO lot snapshot reflects the
    inventory ledger at the moment of the call. Raises
    :class:`InsufficientInventory` if a product line can't be covered
    by available lots — the caller surfaces a 400 so the operator
    knows they need to print more before confirming.
    """
    sale = await _load_sale(session, sale_id)
    lines: list[SaleLineCogs] = []
    total_cost = _ZERO
    for item in sorted(sale.items, key=lambda i: i.line_number):
        kind_value = item.kind.value if isinstance(item.kind, SaleItemKind) else item.kind
        cost: Decimal
        consumption: list[CogsConsumption] = []
        if kind_value == SaleItemKind.PRODUCT.value and item.product_id is not None:
            lots = await _load_product_lots(session, product_id=item.product_id)
            result = compute_cogs(product_id=item.product_id, quantity=item.quantity, lots=lots)
            cost = result.total_cost
            consumption = result.consumption
        elif kind_value == SaleItemKind.JOB.value and item.job_id is not None:
            cost = await _cost_for_job_line(session, job_id=item.job_id, quantity=item.quantity)
        else:
            cost = _ZERO
        cost = _q(cost)
        total_cost = _q(total_cost + cost)
        lines.append(
            SaleLineCogs(
                line_number=item.line_number,
                kind=kind_value,
                product_id=item.product_id,
                job_id=item.job_id,
                description=item.description,
                quantity=_q(item.quantity),
                unit_price=_q(item.unit_price),
                extended_amount=_q(item.extended_amount),
                cost=cost,
                consumption=consumption,
            )
        )
    return SaleCogsBreakdown(
        sale_id=sale.id,
        sale_number=sale.sale_number,
        state=sale.state.value,
        subtotal=_q(sale.subtotal),
        discount_amount=_q(sale.discount_amount),
        shipping_amount=_q(sale.shipping_amount),
        tax_amount=_q(sale.tax_amount),
        channel_fee_amount=_q(sale.channel_fee_amount),
        total_amount=_q(sale.total_amount),
        total_cost=total_cost,
        lines=lines,
    )


# ---------------------------------------------------------------------------
# Public: post_for_sale
# ---------------------------------------------------------------------------


async def post_for_sale(
    sale_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
) -> PostResult:
    """Post inventory + journal entries for a confirmed sale.

    See module docstring for the atomicity invariant. ``actor_user_id``
    is used as the actor on every emitted event + the journal entry's
    ``actor_user_id`` FK; if ``None``, the sale's ``created_by_user_id``
    is used as fallback (so service-layer tests that pass ``None`` still
    persist a valid FK).
    """
    sale = await _load_sale(session, sale_id)
    channel = await _load_channel(session, sale.channel_id)
    effective_actor: uuid.UUID = actor_user_id or sale.created_by_user_id

    cogs_account_id = await _require_account(
        session,
        key="sales_posting.cogs_account_id",
        why="debit COGS for confirmed sales",
    )
    ar_account_id = await _require_account(
        session,
        key="sales_posting.default_ar_account_id",
        why="debit accounts-receivable for the sale's gross total",
    )
    if channel.default_revenue_account_id is None:
        raise MissingSalesPostingAccountError(
            f"configure default sales-posting accounts: channel {channel.slug!r} has "
            f"no default_revenue_account_id (needed to credit revenue)"
        )
    revenue_account_id = channel.default_revenue_account_id
    inventory_account_id = await _require_account(
        session,
        key="sales_posting.default_inventory_account_id",
        why="credit inventory for the FIFO cost of consumed lots",
    )

    tax_amount = _q(sale.tax_amount)
    sales_tax_payable_account_id: uuid.UUID | None = None
    if tax_amount > _ZERO:
        sales_tax_payable_account_id = await _require_account(
            session,
            key="sales_posting.sales_tax_payable_account_id",
            why="credit sales tax payable on a sale with tax",
        )

    channel_fee_amount = _q(sale.channel_fee_amount)
    channel_fee_account_id: uuid.UUID | None = None
    if channel_fee_amount > _ZERO:
        if channel.default_fee_account_id is None:
            raise MissingSalesPostingAccountError(
                f"configure default sales-posting accounts: channel {channel.slug!r} "
                f"has no default_fee_account_id (needed to record channel fees)"
            )
        channel_fee_account_id = channel.default_fee_account_id

    # --- Line costing + inventory consumption ---
    total_line_cost = _ZERO
    inventory_tx_ids: list[uuid.UUID] = []
    for item in sorted(sale.items, key=lambda i: i.line_number):
        kind_value = item.kind.value if isinstance(item.kind, SaleItemKind) else item.kind
        if kind_value == SaleItemKind.PRODUCT.value and item.product_id is not None:
            lots = await _load_product_lots(session, product_id=item.product_id)
            cogs_result = compute_cogs(
                product_id=item.product_id,
                quantity=item.quantity,
                lots=lots,
            )
            total_line_cost = _q(total_line_cost + cogs_result.total_cost)
            for consumed in cogs_result.consumption:
                location_id = await _resolve_lot_location_id(session, lot_id=consumed.lot_id)
                tx = await inventory_tx_service.record(
                    session,
                    kind=KIND_SALE_CONSUMPTION,
                    entity_kind=ENTITY_KIND_PRODUCT,
                    entity_id=item.product_id,
                    location_id=location_id,
                    quantity=consumed.quantity,
                    actor_user_id=effective_actor,
                    unit_cost=consumed.unit_cost,
                    linked_sale_id=sale.id,
                    reason=(
                        f"sale {sale.sale_number} line {item.line_number} " f"lot {consumed.lot_id}"
                    ),
                )
                inventory_tx_ids.append(tx.id)
        elif kind_value == SaleItemKind.JOB.value and item.job_id is not None:
            job_cost = await _cost_for_job_line(session, job_id=item.job_id, quantity=item.quantity)
            total_line_cost = _q(total_line_cost + job_cost)
        # MANUAL: cost basis zero (Phase 6.7 will add operator costs).

    # --- Build journal entry ---
    posted_at = datetime.now(UTC)
    subtotal = _q(sale.subtotal)
    discount_amount = _q(sale.discount_amount)
    shipping_amount = _q(sale.shipping_amount)
    total_amount = _q(sale.total_amount)
    revenue_amount = _q(subtotal - discount_amount + shipping_amount)

    lines_in: list[journal_service.JournalLineInput] = []
    line_no = 0

    def _next_line_no() -> int:
        nonlocal line_no
        line_no += 1
        return line_no

    if total_line_cost > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=cogs_account_id,
                debit=total_line_cost,
                credit=_ZERO,
                line_number=_next_line_no(),
                memo=f"COGS for sale {sale.sale_number}",
            )
        )
    if total_amount > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=ar_account_id,
                debit=total_amount,
                credit=_ZERO,
                line_number=_next_line_no(),
                memo=f"AR gross for sale {sale.sale_number}",
            )
        )
    if channel_fee_amount > _ZERO and channel_fee_account_id is not None:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=channel_fee_account_id,
                debit=channel_fee_amount,
                credit=_ZERO,
                line_number=_next_line_no(),
                memo=f"Channel fee for sale {sale.sale_number}",
            )
        )
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=ar_account_id,
                debit=_ZERO,
                credit=channel_fee_amount,
                line_number=_next_line_no(),
                memo=f"Channel fee offset against AR for sale {sale.sale_number}",
            )
        )
    if total_line_cost > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=inventory_account_id,
                debit=_ZERO,
                credit=total_line_cost,
                line_number=_next_line_no(),
                memo=f"Inventory drawdown for sale {sale.sale_number}",
            )
        )
    if revenue_amount > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=revenue_account_id,
                debit=_ZERO,
                credit=revenue_amount,
                line_number=_next_line_no(),
                memo=f"Revenue for sale {sale.sale_number}",
            )
        )
    if tax_amount > _ZERO and sales_tax_payable_account_id is not None:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=sales_tax_payable_account_id,
                debit=_ZERO,
                credit=tax_amount,
                line_number=_next_line_no(),
                memo=f"Sales tax payable for sale {sale.sale_number}",
            )
        )

    if len(lines_in) < 2:
        raise CogsServiceError(
            f"sale {sale.sale_number} has nothing to post " f"(subtotal, tax, fees all zero)"
        )

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Sale {sale.sale_number}: posting",
            posted_at=posted_at,
            lines=lines_in,
        ),
        session=session,
        actor_user_id=effective_actor,
        _internal_skip_approval_check=True,
    )
    # _internal_skip_approval_check guarantees a JournalEntry, not an
    # ApprovalRequest — narrow for the type checker.
    assert isinstance(entry, JournalEntry)
    journal_entry_id: uuid.UUID = entry.id

    # Persist the FK on the sale so the cancel path can find this entry
    # without a description-string scan. Same TX as the post above.
    sale.posting_journal_entry_id = journal_entry_id
    await session.flush()

    result = PostResult(
        journal_entry_id=journal_entry_id,
        inventory_transaction_ids=inventory_tx_ids,
        total_cost=total_line_cost,
    )

    # Emit the audit trail event LAST so it's only present when
    # everything else succeeded. (Inside the same TX, so rollback still
    # discards it if a later step in the caller raises.)
    await event_store.append(
        EventCreate(
            type=sales_events.TYPE_SALE_POSTED,
            aggregate_type=sales_events.AGGREGATE_TYPE_SALE,
            aggregate_id=sale.id,
            payload={
                "sale_id": str(sale.id),
                "sale_number": sale.sale_number,
                "journal_entry_id": str(journal_entry_id),
                "inventory_transaction_ids": [str(t) for t in inventory_tx_ids],
                "total_amount": str(total_amount),
            },
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=effective_actor,
        ),
        session=session,
    )
    return result


# ---------------------------------------------------------------------------
# Public: reverse_for_sale
# ---------------------------------------------------------------------------


async def reverse_for_sale(
    sale_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
) -> PostResult:
    """Reverse a previously-posted sale: restore inventory + reverse JE.

    Invoked from :func:`app.services.sales.cancel` when cancelling a
    sale that was previously confirmed. Returns a no-op (empty IDs,
    zero cost) when no posted journal entry exists — that's the case
    for sales cancelled directly from ``draft`` and the caller is free
    to skip emitting SaleReversed.
    """
    sale = await _load_sale(session, sale_id)
    effective_actor: uuid.UUID = actor_user_id or sale.created_by_user_id

    # Locate the original journal entry via the FK populated at confirm
    # time. The caller (sales.cancel) only invokes this function when
    # the sale was previously confirmed, so a NULL FK here means the
    # row was created before this column existed — raise loudly rather
    # than silently scanning the GL by description.
    if sale.posting_journal_entry_id is None:
        raise CogsServiceError(
            f"sale {sale.sale_number} has no posting_journal_entry_id; "
            "cannot reverse (data created before column existed?)"
        )
    original = (
        await session.execute(
            select(JournalEntry).where(JournalEntry.id == sale.posting_journal_entry_id)
        )
    ).scalar_one_or_none()
    if original is None:
        raise CogsServiceError(
            f"sale {sale.sale_number} references journal_entry "
            f"{sale.posting_journal_entry_id} which does not exist"
        )

    # Restore inventory: walk the prior sale_consumption rows and emit
    # inverse positive rows under kind=return_in (existing positive
    # kind in the enum — no new value needed).
    stmt2 = (
        select(InventoryTransaction)
        .where(InventoryTransaction.linked_sale_id == sale.id)
        .where(InventoryTransaction.kind == KIND_SALE_CONSUMPTION)
        .order_by(asc(InventoryTransaction.occurred_at), asc(InventoryTransaction.id))
    )
    consumption_rows = list((await session.execute(stmt2)).scalars().all())

    inventory_tx_ids: list[uuid.UUID] = []
    for row in consumption_rows:
        magnitude = _q(abs(row.quantity))
        if magnitude <= _ZERO:
            continue
        tx = await inventory_tx_service.record(
            session,
            kind="return_in",
            entity_kind=row.entity_kind,
            entity_id=row.entity_id,
            location_id=row.location_id,
            quantity=magnitude,
            actor_user_id=effective_actor,
            unit_cost=row.unit_cost_at_transaction,
            linked_sale_id=sale.id,
            reason=f"reversal of sale {sale.sale_number} consumption {row.id}",
        )
        inventory_tx_ids.append(tx.id)

    reversal = await journal_service.reverse(
        original.id,
        session=session,
        actor_user_id=effective_actor,
        description=f"Reversal of sale {sale.sale_number}",
    )

    result = PostResult(
        journal_entry_id=reversal.id,
        inventory_transaction_ids=inventory_tx_ids,
        total_cost=_ZERO,
    )

    await event_store.append(
        EventCreate(
            type=sales_events.TYPE_SALE_REVERSED,
            aggregate_type=sales_events.AGGREGATE_TYPE_SALE,
            aggregate_id=sale.id,
            payload={
                "sale_id": str(sale.id),
                "sale_number": sale.sale_number,
                "reversing_journal_entry_id": str(reversal.id),
                "original_journal_entry_id": str(original.id),
                "inventory_transaction_ids": [str(t) for t in inventory_tx_ids],
            },
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=effective_actor,
        ),
        session=session,
    )
    return result


__all__ = [
    "CogsServiceError",
    "InsufficientInventory",
    "MissingSalesPostingAccountError",
    "PostResult",
    "SaleCogsBreakdown",
    "SaleLineCogs",
    "post_for_sale",
    "preview",
    "reverse_for_sale",
]
