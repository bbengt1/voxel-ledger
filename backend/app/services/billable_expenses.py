"""Billable expenses service (Phase 8.8, #135).

Operator workflow
-----------------

1. An operator flags a ``bill_item`` or ``expense_claim_line`` as
   ``is_billable`` with a target ``customer_id``. Phase 8.7 already wired
   the columns on ``expense_claim_line``; Phase 8.8 adds them to
   ``bill_item`` (see migration 0046).
2. Later, the invoice composer (``app.services.invoices.create_draft`` /
   ``update_draft``) accepts a per-line ``billable_source`` reference.
   For each such line:

   * the composer loads the source via :func:`load_source`,
   * validates ``source.customer_id == invoice.customer_id``,
     ``source.is_billable is True``, and
     ``source.billed_invoice_item_id is None``,
   * computes the line amount via :func:`compute_billed_amount` using
     ``source.markup_percent`` (or a per-line override from the API),
   * flushes the new ``invoice_item``, then
   * calls :func:`mark_billed` to stamp ``billed_invoice_item_id`` on
     the source.

Same-TX invariant
-----------------

The link operation MUST share the caller's database transaction. None of
the functions here commit; the caller (invoice composer) commits or rolls
back atomically. Mirrors the same-TX rule documented in
``app.services.invoices`` for invoice issuance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ap as ap_events
from app.events.types import ar as ar_events
from app.models.bill import Bill, BillItem
from app.models.expense_claim import ExpenseClaim, ExpenseClaimLine
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BillableExpensesServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class InvalidBillableExpenseError(BillableExpensesServiceError):
    """The source row failed validation for billing (already billed,
    not flagged ``is_billable``, or customer mismatch)."""


class BillableExpenseSourceNotFoundError(BillableExpensesServiceError):
    """Mapped to 400 — the operator referenced a source row that doesn't
    exist."""


# ---------------------------------------------------------------------------
# Source kinds
# ---------------------------------------------------------------------------


SOURCE_KIND_BILL_ITEM = "bill_item"
SOURCE_KIND_EXPENSE_CLAIM_LINE = "expense_claim_line"
ALLOWED_SOURCE_KINDS: frozenset[str] = frozenset(
    {SOURCE_KIND_BILL_ITEM, SOURCE_KIND_EXPENSE_CLAIM_LINE}
)


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------


_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def compute_billed_amount(
    *, source_amount: Decimal | str | int | float, markup_percent: Decimal | str | int | float
) -> Decimal:
    """Apply percent markup. ``10 = 10%`` -> ``source * 1.10``.

    Quantized to the standard 6-place Decimal grid used by the AR/AP
    services so the rounded line amount round-trips through Postgres
    cleanly.
    """
    amount = _q(source_amount)
    markup = _q(markup_percent)
    multiplier = Decimal("1") + (markup / _HUNDRED)
    return _q(amount * multiplier)


# ---------------------------------------------------------------------------
# Unbilled row DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnbilledBillItem:
    source_kind: str
    source_id: uuid.UUID
    bill_id: uuid.UUID
    bill_number: str
    line_number: int
    description: str
    amount: Decimal
    markup_percent: Decimal
    occurred_on: date


@dataclass(frozen=True)
class UnbilledExpenseClaimLine:
    source_kind: str
    source_id: uuid.UUID
    claim_id: uuid.UUID
    claim_number: str
    line_number: int
    description: str
    amount: Decimal
    markup_percent: Decimal
    occurred_on: date


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


async def list_unbilled(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
) -> list[UnbilledBillItem | UnbilledExpenseClaimLine]:
    """Return rows flagged billable for ``customer_id`` that aren't billed.

    Bill items use ``bill.issued_at`` (or ``bill.created_at`` if not
    yet issued) for ``occurred_on``. Expense claim lines carry their own
    ``occurred_on`` date.

    Ordered by ``occurred_on`` ascending, then ``source_kind`` then id
    for deterministic output.
    """
    rows: list[UnbilledBillItem | UnbilledExpenseClaimLine] = []

    bill_stmt = (
        select(BillItem)
        .where(BillItem.customer_id == customer_id)
        .where(BillItem.is_billable.is_(True))
        .where(BillItem.billed_invoice_item_id.is_(None))
        .options(selectinload(BillItem.bill))
    )
    for item in (await session.execute(bill_stmt)).scalars().all():
        bill: Bill = item.bill
        occurred_on = (bill.issued_at or bill.created_at).date()
        rows.append(
            UnbilledBillItem(
                source_kind=SOURCE_KIND_BILL_ITEM,
                source_id=item.id,
                bill_id=bill.id,
                bill_number=bill.bill_number,
                line_number=item.line_number,
                description=item.description,
                amount=item.extended_amount,
                markup_percent=item.markup_percent,
                occurred_on=occurred_on,
            )
        )

    claim_stmt = (
        select(ExpenseClaimLine)
        .where(ExpenseClaimLine.customer_id == customer_id)
        .where(ExpenseClaimLine.is_billable.is_(True))
        .where(ExpenseClaimLine.billed_invoice_item_id.is_(None))
        .options(selectinload(ExpenseClaimLine.claim))
    )
    for line in (await session.execute(claim_stmt)).scalars().all():
        claim: ExpenseClaim = line.claim
        rows.append(
            UnbilledExpenseClaimLine(
                source_kind=SOURCE_KIND_EXPENSE_CLAIM_LINE,
                source_id=line.id,
                claim_id=claim.id,
                claim_number=claim.claim_number,
                line_number=line.line_number,
                description=line.description,
                amount=line.amount,
                markup_percent=line.markup_percent,
                occurred_on=line.occurred_on,
            )
        )

    rows.sort(key=lambda r: (r.occurred_on, r.source_kind, str(r.source_id)))
    return rows


# ---------------------------------------------------------------------------
# Source loader
# ---------------------------------------------------------------------------


@dataclass
class SourceRow:
    """Polymorphic view of a billable source — used by the invoice
    composer to read the per-line snapshot fields without caring whether
    the row is a ``bill_item`` or an ``expense_claim_line``."""

    source_kind: str
    source_id: uuid.UUID
    customer_id: uuid.UUID | None
    is_billable: bool
    billed_invoice_item_id: uuid.UUID | None
    amount: Decimal
    markup_percent: Decimal
    description: str
    bill_number: str | None = None
    claim_number: str | None = None
    line_number: int = 0


async def load_source(
    session: AsyncSession,
    *,
    source_kind: str,
    source_id: uuid.UUID,
) -> SourceRow:
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise InvalidBillableExpenseError(f"unknown billable source_kind: {source_kind!r}")
    if source_kind == SOURCE_KIND_BILL_ITEM:
        stmt = select(BillItem).where(BillItem.id == source_id).options(selectinload(BillItem.bill))
        item = (await session.execute(stmt)).scalar_one_or_none()
        if item is None:
            raise BillableExpenseSourceNotFoundError(f"bill_item {source_id} not found")
        return SourceRow(
            source_kind=SOURCE_KIND_BILL_ITEM,
            source_id=item.id,
            customer_id=item.customer_id,
            is_billable=bool(item.is_billable),
            billed_invoice_item_id=item.billed_invoice_item_id,
            amount=item.extended_amount,
            markup_percent=item.markup_percent,
            description=item.description,
            bill_number=item.bill.bill_number if item.bill else None,
            line_number=item.line_number,
        )
    # expense_claim_line
    stmt = (
        select(ExpenseClaimLine)
        .where(ExpenseClaimLine.id == source_id)
        .options(selectinload(ExpenseClaimLine.claim))
    )
    line = (await session.execute(stmt)).scalar_one_or_none()
    if line is None:
        raise BillableExpenseSourceNotFoundError(f"expense_claim_line {source_id} not found")
    return SourceRow(
        source_kind=SOURCE_KIND_EXPENSE_CLAIM_LINE,
        source_id=line.id,
        customer_id=line.customer_id,
        is_billable=bool(line.is_billable),
        billed_invoice_item_id=line.billed_invoice_item_id,
        amount=line.amount,
        markup_percent=line.markup_percent,
        description=line.description,
        claim_number=line.claim.claim_number if line.claim else None,
        line_number=line.line_number,
    )


def describe_source(source: SourceRow) -> str:
    """Default per-line description used when the invoice line doesn't
    supply one. Mirrors the spec example:
    ``"BILL-2026-0001 L1: Office supplies"`` for bills,
    ``"EXP-2026-0001 L1: Taxi"`` for claims."""
    prefix = source.bill_number or source.claim_number or source.source_kind
    return f"{prefix} L{source.line_number}: {source.description}"


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------


async def mark_billed(
    session: AsyncSession,
    *,
    source_kind: str,
    source_id: uuid.UUID,
    invoice_id: uuid.UUID,
    invoice_item_id: uuid.UUID,
    customer_id: uuid.UUID,
    source_amount: Decimal,
    billed_amount: Decimal,
    markup_percent: Decimal,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Stamp ``billed_invoice_item_id`` on the source row + emit the link
    event.

    Idempotency: if ``billed_invoice_item_id`` is already set on the source
    (even by a prior call within the same transaction), raises
    :class:`InvalidBillableExpenseError`. Same-TX with the caller — does
    not commit.
    """
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise InvalidBillableExpenseError(f"unknown billable source_kind: {source_kind!r}")

    if source_kind == SOURCE_KIND_BILL_ITEM:
        stmt = select(BillItem).where(BillItem.id == source_id)
        item = (await session.execute(stmt)).scalar_one_or_none()
        if item is None:
            raise BillableExpenseSourceNotFoundError(f"bill_item {source_id} not found")
        if item.billed_invoice_item_id is not None:
            raise InvalidBillableExpenseError(
                f"bill_item {source_id} is already linked to invoice_item "
                f"{item.billed_invoice_item_id}; cannot re-bill"
            )
        item.billed_invoice_item_id = invoice_item_id
    else:
        stmt2 = select(ExpenseClaimLine).where(ExpenseClaimLine.id == source_id)
        line = (await session.execute(stmt2)).scalar_one_or_none()
        if line is None:
            raise BillableExpenseSourceNotFoundError(f"expense_claim_line {source_id} not found")
        if line.billed_invoice_item_id is not None:
            raise InvalidBillableExpenseError(
                f"expense_claim_line {source_id} is already linked to "
                f"invoice_item {line.billed_invoice_item_id}; cannot re-bill"
            )
        line.billed_invoice_item_id = invoice_item_id

    await session.flush()

    payload: dict[str, Any] = {
        "source_kind": source_kind,
        "source_id": str(source_id),
        "invoice_id": str(invoice_id),
        "invoice_item_id": str(invoice_item_id),
        "customer_id": str(customer_id),
        "amount": str(_q(billed_amount)),
        "source_amount": str(_q(source_amount)),
        "markup_percent": str(_q(markup_percent)),
    }
    await event_store.append(
        EventCreate(
            type=ap_events.TYPE_BILLABLE_EXPENSE_LINKED,
            aggregate_type=ar_events.AGGREGATE_TYPE_INVOICE,
            aggregate_id=invoice_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


__all__ = [
    "ALLOWED_SOURCE_KINDS",
    "BillableExpenseSourceNotFoundError",
    "BillableExpensesServiceError",
    "InvalidBillableExpenseError",
    "SOURCE_KIND_BILL_ITEM",
    "SOURCE_KIND_EXPENSE_CLAIM_LINE",
    "SourceRow",
    "UnbilledBillItem",
    "UnbilledExpenseClaimLine",
    "compute_billed_amount",
    "describe_source",
    "list_unbilled",
    "load_source",
    "mark_billed",
]
