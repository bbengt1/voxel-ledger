"""Refunds service (Phase 6.5, #97).

Owns the ``refund`` aggregate + its ``refund_item`` lines. Refund numbers
are allocated via the race-safe reference allocator with prefix ``RF``.

Approval gating
---------------
``total_amount > settings.sales.refund.approval_threshold`` →
state=``pending_approval`` plus an ``ApprovalRequest`` row. The endpoint
maps this to HTTP 202. ``kind=marketplace_initiated`` bypasses the gate
entirely (marketplace already issued the money — we're recording it).

State machine
-------------

    (create over-threshold)            -> pending_approval
    (create under-threshold or         -> approved
     marketplace_initiated)
    pending_approval -> approved       (approve, owner only)
    pending_approval -> rejected       (reject, owner only)
    approved         -> posted         (post — fires inventory + GL
                                        reversal in same TX)
    pending_approval -> cancelled      (cancel)
    approved         -> cancelled      (cancel)

Posting (``post``)
------------------
Loads the prior sale-consumption rows (kind=sale_consumption) for the
sale, slices them proportionally to the refunded extended_amount /
sale_subtotal, and emits ``return_in`` inventory transactions if
``restock_inventory`` is true. The original journal entry is reversed
proportionally — the simplest model is to scale each line by
``refund_total / sale_total_amount`` so the offsetting entry maintains
the same debit/credit structure. Same-TX guarantee: any raise rolls
back state flip + inventory + JE.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import sales as sales_events
from app.models.approval_request import ApprovalRequest, ApprovalState
from app.models.inventory_transaction import (
    KIND_RETURN_IN,
    KIND_SALE_CONSUMPTION,
    InventoryTransaction,
)
from app.models.refund import Refund, RefundItem, RefundKind, RefundState
from app.models.sale import Sale
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import inventory_transactions as inventory_tx_service
from app.services.approvals import ApprovalsService
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RefundsServiceError(Exception):
    """Base. Routers default to 400."""


class RefundNotFoundError(RefundsServiceError):
    """Mapped to 404."""


class SaleNotFoundForRefundError(RefundsServiceError):
    pass


class InvalidRefundItemError(RefundsServiceError):
    pass


class OverRefundError(RefundsServiceError):
    """Refunded qty would exceed the sale_item's remaining refundable qty.

    Mapped to 409 — conflict with existing state."""


class InvalidRefundStateError(RefundsServiceError):
    """Illegal state transition or attempt to mutate a finalized refund."""


class InvalidCursorError(RefundsServiceError):
    pass


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")
_REFUND_THRESHOLD_KEY = "sales.refund.approval_threshold"


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, refund_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(refund_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=sales_events.AGGREGATE_TYPE_REFUND,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _items_payload(items: list[RefundItem]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(i.id),
            "sale_item_id": str(i.sale_item_id),
            "quantity": str(i.quantity),
            "unit_amount": str(i.unit_amount),
            "extended_amount": str(i.extended_amount),
        }
        for i in items
    ]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _load(session: AsyncSession, refund_id: uuid.UUID) -> Refund:
    stmt = select(Refund).where(Refund.id == refund_id).options(selectinload(Refund.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise RefundNotFoundError(str(refund_id))
    return row


async def _load_sale(session: AsyncSession, sale_id: uuid.UUID) -> Sale:
    stmt = select(Sale).where(Sale.id == sale_id).options(selectinload(Sale.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SaleNotFoundForRefundError(f"sale {sale_id} not found")
    return row


async def _already_refunded_qty(
    session: AsyncSession,
    *,
    sale_item_id: uuid.UUID,
    exclude_refund_id: uuid.UUID | None = None,
) -> Decimal:
    """Sum of refunded quantity across all non-rejected, non-cancelled
    refund_items for this sale_item.

    A refund that was rejected or cancelled never consumed the line; a
    refund that's posted, approved, or pending_approval reserves the qty.
    """
    stmt = (
        select(RefundItem.quantity, Refund.state)
        .join(Refund, RefundItem.refund_id == Refund.id)
        .where(RefundItem.sale_item_id == sale_item_id)
    )
    if exclude_refund_id is not None:
        stmt = stmt.where(Refund.id != exclude_refund_id)
    rows = (await session.execute(stmt)).all()
    total = _ZERO
    for qty, state in rows:
        state_value = state.value if hasattr(state, "value") else state
        if state_value in (
            RefundState.REJECTED.value,
            RefundState.CANCELLED.value,
        ):
            continue
        total = _q(total + _q(qty))
    return total


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@dataclass
class RefundCreateResult:
    refund: Refund
    approval_request_id: uuid.UUID | None


async def create(
    *,
    session: AsyncSession,
    sale_id: uuid.UUID,
    kind: str,
    reason_code: str,
    notes: str | None,
    restock_inventory: bool,
    items: list[dict[str, Any]],
    actor_user_id: uuid.UUID,
) -> RefundCreateResult:
    """Create a refund.

    Validates each line against the originating sale_item + the
    already-refunded total. Computes the rolled-up total. Above the
    threshold (and not marketplace_initiated) → state=pending_approval
    plus an ApprovalRequest. Otherwise → state=approved.
    """
    reason_code = (reason_code or "").strip()
    if not reason_code:
        raise RefundsServiceError("reason_code is required")

    try:
        kind_enum = RefundKind(kind)
    except ValueError as exc:
        raise RefundsServiceError(f"invalid refund kind: {kind!r}") from exc

    if not items:
        raise InvalidRefundItemError("refund requires at least one line")

    sale = await _load_sale(session, sale_id)
    sale_items_by_id = {si.id: si for si in sale.items}

    normalized: list[dict[str, Any]] = []
    total = _ZERO
    for raw in items:
        sale_item_id = raw.get("sale_item_id")
        if isinstance(sale_item_id, str):
            try:
                sale_item_id = uuid.UUID(sale_item_id)
            except ValueError as exc:
                raise InvalidRefundItemError(f"invalid sale_item_id: {sale_item_id!r}") from exc
        if sale_item_id not in sale_items_by_id:
            raise InvalidRefundItemError(
                f"sale_item {sale_item_id} is not a line on sale {sale.sale_number}"
            )
        sale_item = sale_items_by_id[sale_item_id]
        try:
            qty = _q(raw.get("quantity", "0"))
            unit_amount = _q(raw.get("unit_amount", "0"))
        except (ArithmeticError, ValueError) as exc:
            raise InvalidRefundItemError(f"invalid numeric value on refund line: {exc}") from exc
        if qty <= _ZERO:
            raise InvalidRefundItemError("refund quantity must be positive")
        if unit_amount < _ZERO:
            raise InvalidRefundItemError("refund unit_amount must be non-negative")

        already = await _already_refunded_qty(session, sale_item_id=sale_item.id)
        remaining = _q(_q(sale_item.quantity) - already)
        if qty > remaining:
            raise OverRefundError(
                f"refund quantity {qty} for sale_item {sale_item.id} exceeds "
                f"remaining refundable quantity {remaining} "
                f"(already refunded {already} of {sale_item.quantity})"
            )
        extended = _q(qty * unit_amount)
        total = _q(total + extended)
        normalized.append(
            {
                "sale_item_id": sale_item.id,
                "quantity": qty,
                "unit_amount": unit_amount,
                "extended_amount": extended,
            }
        )

    # Threshold gating.
    threshold = await SettingsService.get(_REFUND_THRESHOLD_KEY, session=session)
    if threshold is None:
        threshold = Decimal("500.00")
    if not isinstance(threshold, Decimal):
        threshold = Decimal(str(threshold))

    over_threshold = total > threshold and kind_enum != RefundKind.MARKETPLACE_INITIATED
    state = RefundState.PENDING_APPROVAL if over_threshold else RefundState.APPROVED

    refund_number = await ReferenceNumberService.allocate("RF", session=session)

    refund = Refund(
        id=uuid.uuid4(),
        refund_number=refund_number,
        sale_id=sale.id,
        kind=kind_enum,
        state=state,
        total_amount=total,
        restock_inventory=restock_inventory,
        reason_code=reason_code,
        notes=notes,
        created_by_user_id=actor_user_id,
        approved_by_user_id=actor_user_id if state == RefundState.APPROVED else None,
    )
    session.add(refund)
    await session.flush()
    for line in normalized:
        session.add(
            RefundItem(
                id=uuid.uuid4(),
                refund_id=refund.id,
                sale_item_id=line["sale_item_id"],
                quantity=line["quantity"],
                unit_amount=line["unit_amount"],
                extended_amount=line["extended_amount"],
            )
        )
    await session.flush()

    approval_request_id: uuid.UUID | None = None
    if over_threshold:
        approval = await ApprovalsService.create(
            request_type="sales.large_refund",
            subject_kind="refund",
            subject_id=refund.id,
            payload={
                "refund_id": str(refund.id),
                "refund_number": refund.refund_number,
                "sale_id": str(refund.sale_id),
                "total_amount": str(total),
                "reason_code": reason_code,
                "restock_inventory": restock_inventory,
            },
            threshold_amount=threshold,
            session=session,
            actor_user_id=actor_user_id,
        )
        refund.approval_request_id = approval.id
        approval_request_id = approval.id
        await session.flush()

    refund = await _load(session, refund.id)

    await _emit(
        session,
        event_type=sales_events.TYPE_REFUND_CREATED,
        aggregate_id=refund.id,
        payload={
            "refund_id": str(refund.id),
            "refund_number": refund.refund_number,
            "sale_id": str(refund.sale_id),
            "kind": refund.kind.value if isinstance(refund.kind, RefundKind) else refund.kind,
            "state": refund.state.value if isinstance(refund.state, RefundState) else refund.state,
            "total_amount": str(refund.total_amount),
            "restock_inventory": refund.restock_inventory,
            "reason_code": refund.reason_code,
            "notes": refund.notes,
            "approval_request_id": (
                str(refund.approval_request_id) if refund.approval_request_id else None
            ),
            "items": _items_payload(refund.items),
        },
        actor_user_id=actor_user_id,
    )
    return RefundCreateResult(refund=refund, approval_request_id=approval_request_id)


# ---------------------------------------------------------------------------
# Approve / reject / cancel
# ---------------------------------------------------------------------------


def _ensure_state(refund: Refund, allowed: set[RefundState]) -> None:
    current = refund.state if isinstance(refund.state, RefundState) else RefundState(refund.state)
    if current not in allowed:
        raise InvalidRefundStateError(
            f"refund {refund.refund_number} is in state "
            f"{current.value}; expected one of "
            f"{sorted(s.value for s in allowed)}"
        )


async def approve(
    refund_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID,
    decision_note: str | None = None,
) -> Refund:
    refund = await _load(session, refund_id)
    _ensure_state(refund, {RefundState.PENDING_APPROVAL})
    refund.state = RefundState.APPROVED
    refund.approved_by_user_id = actor_user_id
    if refund.approval_request_id is not None:
        approval = (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == refund.approval_request_id)
            )
        ).scalar_one_or_none()
        if approval is not None and approval.state == ApprovalState.PENDING.value:
            await ApprovalsService.approve(
                approval.id,
                session=session,
                approver_user_id=actor_user_id,
                decision_note=decision_note,
            )
    await session.flush()

    await _emit(
        session,
        event_type=sales_events.TYPE_REFUND_APPROVED,
        aggregate_id=refund.id,
        payload={
            "refund_id": str(refund.id),
            "refund_number": refund.refund_number,
            "sale_id": str(refund.sale_id),
            "total_amount": str(refund.total_amount),
            "reason_code": refund.reason_code,
            "approved_by_user_id": str(actor_user_id),
        },
        actor_user_id=actor_user_id,
    )
    return refund


async def reject(
    refund_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID,
    decision_note: str | None = None,
) -> Refund:
    refund = await _load(session, refund_id)
    _ensure_state(refund, {RefundState.PENDING_APPROVAL})
    refund.state = RefundState.REJECTED
    if refund.approval_request_id is not None:
        approval = (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == refund.approval_request_id)
            )
        ).scalar_one_or_none()
        if approval is not None and approval.state == ApprovalState.PENDING.value:
            await ApprovalsService.reject(
                approval.id,
                session=session,
                approver_user_id=actor_user_id,
                decision_note=decision_note,
            )
    await session.flush()

    await _emit(
        session,
        event_type=sales_events.TYPE_REFUND_REJECTED,
        aggregate_id=refund.id,
        payload={
            "refund_id": str(refund.id),
            "refund_number": refund.refund_number,
            "sale_id": str(refund.sale_id),
            "rejected_by_user_id": str(actor_user_id),
        },
        actor_user_id=actor_user_id,
    )
    return refund


async def cancel(
    refund_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID,
) -> Refund:
    refund = await _load(session, refund_id)
    _ensure_state(refund, {RefundState.PENDING_APPROVAL, RefundState.APPROVED})
    refund.state = RefundState.CANCELLED
    if refund.approval_request_id is not None:
        approval = (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == refund.approval_request_id)
            )
        ).scalar_one_or_none()
        if approval is not None and approval.state == ApprovalState.PENDING.value:
            await ApprovalsService.cancel(
                approval.id,
                session=session,
                actor_user_id=actor_user_id,
                actor_is_owner=True,
            )
    await session.flush()

    await _emit(
        session,
        event_type=sales_events.TYPE_REFUND_CANCELLED,
        aggregate_id=refund.id,
        payload={
            "refund_id": str(refund.id),
            "refund_number": refund.refund_number,
            "sale_id": str(refund.sale_id),
        },
        actor_user_id=actor_user_id,
    )
    return refund


# ---------------------------------------------------------------------------
# Post (reverse inventory + journal entry proportionally)
# ---------------------------------------------------------------------------


async def post(
    refund_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID,
) -> Refund:
    """Post the inventory + journal-entry reversal for an approved refund.

    Same-TX guarantee: state flip, inventory restock, reversing journal
    entry, and ``RefundPosted`` event all share the caller's transaction.
    Any raise rolls back everything.
    """
    refund = await _load(session, refund_id)
    _ensure_state(refund, {RefundState.APPROVED})

    sale = await _load_sale(session, refund.sale_id)
    refund_total = _q(refund.total_amount)

    # ---------------- Inventory restock ----------------
    inventory_tx_ids: list[uuid.UUID] = []
    restock_cost = _ZERO  # accumulated cost of restocked units (for COGS reversal)
    if refund.restock_inventory:
        # Pull the prior sale_consumption rows for this sale (oldest first).
        stmt = (
            select(InventoryTransaction)
            .where(InventoryTransaction.linked_sale_id == sale.id)
            .where(InventoryTransaction.kind == KIND_SALE_CONSUMPTION)
            .order_by(asc(InventoryTransaction.occurred_at), asc(InventoryTransaction.id))
        )
        consumption_rows = list((await session.execute(stmt)).scalars().all())

        # Map each consumption row back to its sale_item via the lot
        # being drawn down. We don't have a direct sale_item_id on the
        # inventory row, but each consumption row's entity_id matches
        # the sale_item.product_id. For multiple product lines pointing
        # at the same product this is ambiguous — Phase 6.5 takes the
        # simpler position that restock is proportional per product:
        # we restock up to ``sum(refund qty for sale_items with this
        # product)`` total from the consumption rows in FIFO order.
        product_refund_qty: dict[uuid.UUID, Decimal] = {}
        for ri in refund.items:
            sale_item = next((si for si in sale.items if si.id == ri.sale_item_id), None)
            if sale_item is None or sale_item.product_id is None:
                continue
            product_refund_qty[sale_item.product_id] = _q(
                product_refund_qty.get(sale_item.product_id, _ZERO) + _q(ri.quantity)
            )

        remaining_by_product = dict(product_refund_qty)
        for row in consumption_rows:
            magnitude = _q(abs(row.quantity))
            if magnitude <= _ZERO:
                continue
            product_id = row.entity_id
            want = remaining_by_product.get(product_id, _ZERO)
            if want <= _ZERO:
                continue
            take = want if want < magnitude else magnitude
            tx = await inventory_tx_service.record(
                session,
                kind=KIND_RETURN_IN,
                entity_kind=row.entity_kind,
                entity_id=row.entity_id,
                location_id=row.location_id,
                quantity=take,
                actor_user_id=actor_user_id,
                unit_cost=row.unit_cost_at_transaction,
                linked_sale_id=sale.id,
                reason=(f"refund {refund.refund_number} restock " f"(consumption {row.id})"),
            )
            inventory_tx_ids.append(tx.id)
            restock_cost = _q(restock_cost + _q(take * _q(row.unit_cost_at_transaction)))
            remaining_by_product[product_id] = _q(want - take)

    # ---------------- Journal entry reversal (proportional) ----------------
    # QBO is the sole ledger (epic #312, Phase 5e): enqueue a role-tagged
    # reversing JournalEntry (Dr revenue + Dr sales_tax / Cr bank for the cash
    # refunded, plus Dr inventory / Cr cogs for any restock) via the sync
    # outbox.
    from app.services.quickbooks import outbox as qbo_outbox

    reversing_je_id: uuid.UUID | None = None
    if refund_total > _ZERO:
        sale_total = _q(sale.total_amount)
        ratio = (
            Decimal("1")
            if sale_total <= _ZERO
            else (refund_total / sale_total).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
        )
        refund_tax = _q(_q(sale.tax_amount) * ratio)
        refund_revenue = _q(refund_total - refund_tax)
        qbo_lines: list[dict] = []
        if refund_revenue > _ZERO:
            qbo_lines.append({"role": "revenue", "posting": "debit", "amount": str(refund_revenue)})
        if refund_tax > _ZERO:
            qbo_lines.append(
                {"role": "sales_tax_payable", "posting": "debit", "amount": str(refund_tax)}
            )
        qbo_lines.append({"role": "bank", "posting": "credit", "amount": str(refund_total)})
        if restock_cost > _ZERO:
            qbo_lines.append({"role": "inventory", "posting": "debit", "amount": str(restock_cost)})
            qbo_lines.append({"role": "cogs", "posting": "credit", "amount": str(restock_cost)})
        await qbo_outbox.enqueue(
            session,
            kind="refund",
            local_id=refund.id,
            payload={
                "lines": qbo_lines,
                "private_note": f"Refund {refund.refund_number} of sale {sale.sale_number}",
            },
            op="post",
        )

    refund.state = RefundState.POSTED
    await session.flush()

    # Mark the approval request consumed (idempotency aid).
    if refund.approval_request_id is not None:
        approval = (
            await session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == refund.approval_request_id)
            )
        ).scalar_one_or_none()
        if (
            approval is not None
            and approval.state == ApprovalState.APPROVED.value
            and approval.consumed_at is None
        ):
            await ApprovalsService.mark_consumed(approval.id, session=session)

    await _emit(
        session,
        event_type=sales_events.TYPE_REFUND_POSTED,
        aggregate_id=refund.id,
        payload={
            "refund_id": str(refund.id),
            "refund_number": refund.refund_number,
            "sale_id": str(refund.sale_id),
            "total_amount": str(refund.total_amount),
            "reason_code": refund.reason_code,
            "reversing_journal_entry_id": (str(reversing_je_id) if reversing_je_id else None),
            "inventory_transaction_ids": [str(t) for t in inventory_tx_ids],
        },
        actor_user_id=actor_user_id,
    )
    return refund


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(refund_id: uuid.UUID, *, session: AsyncSession) -> Refund:
    return await _load(session, refund_id)


@dataclass
class RefundPage:
    items: list[Refund]
    next_cursor: str | None


async def list_refunds(
    *,
    session: AsyncSession,
    state: str | None = None,
    sale_id: uuid.UUID | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> RefundPage:
    stmt = select(Refund).options(selectinload(Refund.items))
    if state is not None:
        try:
            state_enum = RefundState(state)
        except ValueError as exc:
            raise RefundsServiceError(f"invalid state filter: {state!r}") from exc
        stmt = stmt.where(Refund.state == state_enum)
    if sale_id is not None:
        stmt = stmt.where(Refund.sale_id == sale_id)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Refund.created_at < anchor_ts,
                and_(Refund.created_at == anchor_ts, Refund.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Refund.created_at), desc(Refund.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return RefundPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "InvalidCursorError",
    "InvalidRefundItemError",
    "InvalidRefundStateError",
    "OverRefundError",
    "RefundCreateResult",
    "RefundNotFoundError",
    "RefundPage",
    "RefundsServiceError",
    "SaleNotFoundForRefundError",
    "approve",
    "cancel",
    "create",
    "get",
    "list_refunds",
    "post",
    "reject",
]


# ---------------------------------------------------------------------------
# Subject-resolver registration (Phase 4.4 approvals integration)
# ---------------------------------------------------------------------------
# The approvals module's ``subject_resolver`` registry maps subject_kind ->
# loader. Phase 6.5 wires "refund" to this service's ``get``. Defensive try
# block — the registry is optional (added in this phase) and must not be
# load-bearing for module import.
try:  # pragma: no cover
    from app.services import approvals as _approvals_module

    if hasattr(_approvals_module, "register_subject_resolver"):
        _approvals_module.register_subject_resolver("refund", get)
except Exception:
    pass
