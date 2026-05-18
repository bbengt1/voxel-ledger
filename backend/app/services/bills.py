"""Bills service (Phase 8.2, #129).

The bill is the AP system-of-record — the direct AP-side mirror of
the Phase 7.3 ``invoice``. Issuing a bill (``draft -> issued``) posts
to the GL atomically INSIDE THE SAME DB TRANSACTION as the state flip.
This same-TX invariant is the keystone v2 rule for AP (mirrors AR): if
any step (re-snapshot, account resolve, JE post, event emit) raises,
the outer transaction rolls back and NOTHING persists — not the state
flip, not the JE, not the audit events. Do not introduce nested commits.

Account resolution at issue time
--------------------------------
* Expense Dr (per line):
  ``line.expense_account_id_override`` ->
  ``expense_category.default_expense_account_id`` (Phase 8.6; skipped
  today since the table doesn't exist) ->
  ``vendor.default_expense_account_id`` ->
  setting ``ap.default_expense_account_id`` ->
  raise ``MissingApPostingAccountError``.
* AP Cr (total):
  ``vendor.default_ap_account_id`` ->
  setting ``ap.default_ap_account_id`` ->
  raise.
* Tax Dr (when ``tax_amount > 0``):
  setting ``ap.default_tax_expense_account_id`` -> raise.

  v2 keeps tax handling simple: the tax portion of a bill is treated
  as a non-recoverable expense Dr to a dedicated account. Phase 9 may
  split into a recoverable-tax-asset path. The AP mirror of invoices'
  sales-tax-payable requirement.

Posting math (mirrors invoices in reverse)
------------------------------------------
* Cr AP account = ``total_amount`` (tax-inclusive).
* Dr per-line expense = ``line.extended_amount`` (un-discounted).
* If ``discount_amount > 0`` we don't post a separate contra-expense
  line — the discount is implicitly bundled into the AP credit math,
  matching how invoices handle discount (the discount reduces the
  revenue credit by being subtracted from subtotal). For bills the AP
  Cr is ``total = subtotal - discount + tax``, and the Dr legs sum to
  ``subtotal + tax``. To keep the entry balanced when discount > 0 we
  emit a contra-Dr discount expense line equal to ``-discount_amount``
  on the same primary expense account... actually invoices solved this
  by setting revenue_amount = subtotal - discount (i.e. the discount is
  absorbed into the revenue side). Mirroring: we set the expense Dr per
  line to extended_amount, but to keep the entry balanced when discount
  > 0 we Cr the primary expense account by discount_amount. In practice
  v2 ships with discount = 0 on bills; this code path raises a clear
  error if discount > 0 and refuses to post until Phase 9 lands the
  proper purchase-discounts-earned account.

Void flow
---------
Mirror ``invoices.void``: reverses the JE in same TX, only allowed from
``issued`` / ``partially_paid`` / ``overdue``, raises
``BillHasPaymentsError`` if ``amount_paid > 0`` (Phase 8.3 will land
``bill_payment`` and the unapply flow).
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ap as ap_events
from app.models.bill import (
    Bill,
    BillItem,
    BillItemKind,
    BillState,
)
from app.models.journal_entry import JournalEntry
from app.models.vendor import Vendor
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import expense_categories as expense_categories_service
from app.services import journal_entries as journal_service
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BillServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class BillNotFoundError(BillServiceError):
    """Mapped to 404."""


class VendorNotFoundForBillError(BillServiceError):
    """The referenced vendor doesn't exist."""


class InvalidBillItemError(BillServiceError):
    """Line failed validation (kind/ref mismatch, bad qty/price)."""


class InvalidBillStateError(BillServiceError):
    """Illegal state transition or write-while-not-draft."""


class MissingApPostingAccountError(BillServiceError):
    """Required AP posting account (or fallback chain) isn't set.

    Mapped to 400 with a clear "configure default AP posting accounts"
    message — the operator must set the GL account IDs via the settings
    endpoint before any bill can issue.
    """


class BillHasPaymentsError(BillServiceError):
    """Voiding a bill that already has payments applied is illegal
    until Phase 8.3 lands the unapply flow."""


class InvalidCursorError(BillServiceError):
    pass


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


_TRANSITIONS: dict[BillState, frozenset[BillState]] = {
    BillState.DRAFT: frozenset({BillState.ISSUED, BillState.VOID}),
    BillState.ISSUED: frozenset(
        {
            BillState.PARTIALLY_PAID,
            BillState.PAID,
            BillState.OVERDUE,
            BillState.VOID,
        }
    ),
    BillState.PARTIALLY_PAID: frozenset({BillState.PAID, BillState.OVERDUE, BillState.VOID}),
    BillState.OVERDUE: frozenset({BillState.PARTIALLY_PAID, BillState.PAID, BillState.VOID}),
    BillState.PAID: frozenset(),
    BillState.VOID: frozenset(),
}


def _ensure_transition(current: BillState, target: BillState) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidBillStateError(
            f"cannot transition bill from {current.value} to {target.value}"
        )


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, bill_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(bill_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Event emission helper
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
            aggregate_type=ap_events.AGGREGATE_TYPE_BILL,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Item validation
# ---------------------------------------------------------------------------


def _coerce_kind(value: str | BillItemKind) -> BillItemKind:
    if isinstance(value, BillItemKind):
        return value
    try:
        return BillItemKind(value)
    except ValueError as exc:
        raise InvalidBillItemError(f"invalid item kind: {value!r}") from exc


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    kind = _coerce_kind(item.get("kind"))
    expense_category_id = item.get("expense_category_id")
    override = item.get("expense_account_id_override")
    if isinstance(expense_category_id, str):
        try:
            expense_category_id = uuid.UUID(expense_category_id)
        except ValueError as exc:
            raise InvalidBillItemError(
                f"invalid expense_category_id: {expense_category_id!r}"
            ) from exc
    if isinstance(override, str):
        try:
            override = uuid.UUID(override)
        except ValueError as exc:
            raise InvalidBillItemError(
                f"invalid expense_account_id_override: {override!r}"
            ) from exc

    description = (item.get("description") or "").strip()
    vendor_sku = item.get("vendor_sku")

    if not description:
        raise InvalidBillItemError("item description is required")

    if kind == BillItemKind.EXPENSE_CATEGORY:
        if expense_category_id is None:
            raise InvalidBillItemError("kind=expense_category requires expense_category_id")
    else:  # MANUAL
        # expense_category_id MAY be null for manual; we don't forbid setting
        # it (the check constraint only forbids the inverse — kind=expense_
        # category without an id). Mirror invoice 'manual': forbid the ref.
        if expense_category_id is not None:
            raise InvalidBillItemError("kind=manual requires expense_category_id be null")

    try:
        quantity = _q(item.get("quantity", "1"))
        unit_price = _q(item.get("unit_price", "0"))
    except (ArithmeticError, ValueError) as exc:
        raise InvalidBillItemError(f"invalid numeric value on item: {exc}") from exc

    if quantity <= 0:
        raise InvalidBillItemError("quantity must be positive")
    if unit_price < 0:
        raise InvalidBillItemError("unit_price must be non-negative")

    return {
        "kind": kind,
        "expense_category_id": expense_category_id,
        "description": description,
        "vendor_sku": vendor_sku,
        "quantity": quantity,
        "unit_price": unit_price,
        "expense_account_id_override": override,
    }


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Totals:
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


def _compute_totals(
    *,
    items: list[dict[str, Any]],
    discount_amount: Decimal,
    tax_amount: Decimal,
) -> _Totals:
    subtotal = Decimal("0")
    for item in items:
        ext = _q(item["quantity"] * item["unit_price"])
        item["extended_amount"] = ext
        subtotal += ext
    subtotal = _q(subtotal)
    discount = _q(discount_amount)
    tax = _q(tax_amount)
    total = _q(subtotal - discount + tax)
    return _Totals(
        subtotal=subtotal,
        discount_amount=discount,
        tax_amount=tax,
        total_amount=total,
    )


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------


async def _load(
    session: AsyncSession,
    bill_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> Bill:
    stmt = select(Bill).where(Bill.id == bill_id)
    if with_items:
        stmt = stmt.options(selectinload(Bill.items))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise BillNotFoundError(str(bill_id))
    if with_items:
        await session.refresh(row, ["items"])
    return row


async def _load_vendor(session: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    stmt = select(Vendor).where(Vendor.id == vendor_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise VendorNotFoundForBillError(str(vendor_id))
    return row


def _payload_items(items: list[BillItem]) -> list[dict[str, Any]]:
    return [
        {
            "line_number": i.line_number,
            "kind": i.kind.value if isinstance(i.kind, BillItemKind) else i.kind,
            "expense_category_id": str(i.expense_category_id) if i.expense_category_id else None,
            "description": i.description,
            "vendor_sku": i.vendor_sku,
            "quantity": str(i.quantity),
            "unit_price": str(i.unit_price),
            "extended_amount": str(i.extended_amount),
            "expense_account_id_override": (
                str(i.expense_account_id_override) if i.expense_account_id_override else None
            ),
        }
        for i in sorted(items, key=lambda x: x.line_number)
    ]


def _created_payload(bill: Bill) -> dict[str, Any]:
    return {
        "bill_id": str(bill.id),
        "bill_number": bill.bill_number,
        "vendor_id": str(bill.vendor_id),
        "state": bill.state.value,
        "issued_at": bill.issued_at.isoformat() if bill.issued_at else None,
        "due_at": bill.due_at.isoformat() if bill.due_at else None,
        "vendor_invoice_number": bill.vendor_invoice_number,
        "subtotal": str(bill.subtotal),
        "discount_amount": str(bill.discount_amount),
        "tax_amount": str(bill.tax_amount),
        "total_amount": str(bill.total_amount),
        "currency": bill.currency,
        "notes": bill.notes,
        "billing_address_snapshot": bill.billing_address_snapshot,
        "items": _payload_items(bill.items),
    }


# ---------------------------------------------------------------------------
# CRUD: create / update draft
# ---------------------------------------------------------------------------


async def create_draft(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    due_at: datetime | None = None,
    vendor_invoice_number: str | None = None,
    discount_amount: Decimal | str | int | float = Decimal("0"),
    tax_amount: Decimal | str | int | float = Decimal("0"),
    notes: str | None = None,
    items: list[dict[str, Any]] | None = None,
    currency: str = "USD",
    actor_user_id: uuid.UUID,
) -> Bill:
    """Allocate ``BILL-YYYY-NNNN`` and create a draft bill.

    Snapshots ``vendor.billing_address`` onto the bill so later edits of
    the vendor don't rewrite an already-issued bill's address. The
    tentative ``due_at`` (issued_at + payment_terms_days) is recomputed
    at issue time; if the caller supplies one here, it's stored as-is
    on the draft and will be re-computed at issue.
    """
    vendor = await _load_vendor(session, vendor_id)

    normalized_items: list[dict[str, Any]] = []
    for raw in items or []:
        normalized_items.append(_validate_item(raw))

    totals = _compute_totals(
        items=normalized_items,
        discount_amount=_q(discount_amount),
        tax_amount=_q(tax_amount),
    )

    bill_number = await ReferenceNumberService.allocate("BILL", session=session)

    billing_snapshot = dict(vendor.billing_address) if vendor.billing_address is not None else None

    tentative_due_at = due_at
    if tentative_due_at is None and vendor.payment_terms_days is not None:
        tentative_due_at = datetime.now(UTC) + timedelta(days=vendor.payment_terms_days)

    bill = Bill(
        bill_number=bill_number,
        vendor_id=vendor_id,
        state=BillState.DRAFT,
        due_at=tentative_due_at,
        vendor_invoice_number=vendor_invoice_number,
        subtotal=totals.subtotal,
        discount_amount=totals.discount_amount,
        tax_amount=totals.tax_amount,
        total_amount=totals.total_amount,
        amount_paid=_ZERO,
        amount_outstanding=totals.total_amount,
        currency=currency,
        notes=notes,
        billing_address_snapshot=billing_snapshot,
        created_by_user_id=actor_user_id,
    )
    session.add(bill)
    await session.flush()

    for idx, item in enumerate(normalized_items, start=1):
        session.add(
            BillItem(
                bill_id=bill.id,
                line_number=idx,
                kind=item["kind"],
                expense_category_id=item["expense_category_id"],
                description=item["description"],
                vendor_sku=item["vendor_sku"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                extended_amount=item["extended_amount"],
                expense_account_id_override=item["expense_account_id_override"],
            )
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        raise InvalidBillItemError(f"bill item integrity violation: {exc.orig}") from exc

    bill = await _load(session, bill.id)

    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_CREATED,
        aggregate_id=bill.id,
        payload=_created_payload(bill),
        actor_user_id=actor_user_id,
    )
    return bill


_EDITABLE_SCALAR_FIELDS = (
    "vendor_id",
    "due_at",
    "vendor_invoice_number",
    "discount_amount",
    "tax_amount",
    "notes",
)


def _serialize_field(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def update_draft(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Bill:
    bill = await _load(session, bill_id)
    if bill.state != BillState.DRAFT:
        raise InvalidBillStateError(
            f"bill {bill_id} is in state {bill.state.value}; " "only draft bills can be edited"
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_SCALAR_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field in ("discount_amount", "tax_amount") and new_value is not None:
            new_value = _q(new_value)
        if field == "vendor_id" and new_value is not None:
            new_vendor = await _load_vendor(session, new_value)
            bill.billing_address_snapshot = (
                dict(new_vendor.billing_address) if new_vendor.billing_address is not None else None
            )
        current = getattr(bill, field)
        if isinstance(current, Decimal) and isinstance(new_value, Decimal):
            if current == new_value:
                continue
        elif current == new_value:
            continue
        before[field] = _serialize_field(current)
        after[field] = _serialize_field(new_value)
        setattr(bill, field, new_value)

    items_changed = False
    if "items" in patch and patch["items"] is not None:
        items_changed = True
        normalized_items = [_validate_item(raw) for raw in patch["items"]]
        for item in normalized_items:
            item["extended_amount"] = _q(item["quantity"] * item["unit_price"])
        before["items"] = _payload_items(bill.items)
        for existing in list(bill.items):
            await session.delete(existing)
        await session.flush()
        bill.items.clear()
        for idx, item in enumerate(normalized_items, start=1):
            session.add(
                BillItem(
                    bill_id=bill.id,
                    line_number=idx,
                    kind=item["kind"],
                    expense_category_id=item["expense_category_id"],
                    description=item["description"],
                    vendor_sku=item["vendor_sku"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    extended_amount=item["extended_amount"],
                    expense_account_id_override=item["expense_account_id_override"],
                )
            )
        try:
            await session.flush()
        except IntegrityError as exc:
            raise InvalidBillItemError(f"bill item integrity violation: {exc.orig}") from exc

    if not before and not items_changed:
        return bill

    bill = await _load(session, bill.id)
    line_dicts = [{"quantity": line.quantity, "unit_price": line.unit_price} for line in bill.items]
    totals = _compute_totals(
        items=line_dicts,
        discount_amount=bill.discount_amount,
        tax_amount=bill.tax_amount,
    )
    bill.subtotal = totals.subtotal
    bill.discount_amount = totals.discount_amount
    bill.tax_amount = totals.tax_amount
    bill.total_amount = totals.total_amount
    bill.amount_outstanding = _q(totals.total_amount - _q(bill.amount_paid))
    after["totals"] = {
        "subtotal": str(totals.subtotal),
        "discount_amount": str(totals.discount_amount),
        "tax_amount": str(totals.tax_amount),
        "total_amount": str(totals.total_amount),
    }
    if items_changed:
        after["items"] = _payload_items(bill.items)

    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_UPDATED,
        aggregate_id=bill.id,
        payload={
            "bill_id": str(bill.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return bill


# ---------------------------------------------------------------------------
# Account resolution at issue time
# ---------------------------------------------------------------------------


async def _resolve_setting_account(
    session: AsyncSession,
    *,
    keys: tuple[str, ...],
    why: str,
) -> uuid.UUID:
    """Try each ``keys`` in order; return the first set value or raise."""
    for key in keys:
        value = await SettingsService.get(key, session=session)
        if value is not None:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(str(value))
            return value
    pretty = ", ".join(repr(k) for k in keys)
    raise MissingApPostingAccountError(
        f"configure default AP posting accounts: none of {pretty} are set " f"(needed to {why})"
    )


async def _resolve_expense_account(
    session: AsyncSession,
    *,
    line: BillItem,
    vendor: Vendor,
) -> uuid.UUID:
    """Resolve the per-line Dr expense account.

    Chain: line.expense_account_id_override ->
    ``expense_category.default_expense_account_id`` (when the line
    references a category) -> vendor.default_expense_account_id ->
    setting ``ap.default_expense_account_id`` -> raise.
    """
    if line.expense_account_id_override is not None:
        return line.expense_account_id_override
    category_account = await expense_categories_service.get_default_account_for_category(
        session, line.expense_category_id
    )
    if category_account is not None:
        return category_account
    if vendor.default_expense_account_id is not None:
        return vendor.default_expense_account_id
    return await _resolve_setting_account(
        session,
        keys=("ap.default_expense_account_id",),
        why="debit expense for a bill line",
    )


async def _resolve_ap_account(
    session: AsyncSession,
    *,
    vendor: Vendor,
) -> uuid.UUID:
    if vendor.default_ap_account_id is not None:
        return vendor.default_ap_account_id
    return await _resolve_setting_account(
        session,
        keys=("ap.default_ap_account_id",),
        why="credit AP for the bill total",
    )


async def _resolve_tax_expense_account(session: AsyncSession) -> uuid.UUID:
    return await _resolve_setting_account(
        session,
        keys=("ap.default_tax_expense_account_id",),
        why="debit tax expense on a bill with tax",
    )


# ---------------------------------------------------------------------------
# State transitions: issue / void
# ---------------------------------------------------------------------------


async def issue(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Bill:
    """Move ``draft -> issued`` and post the journal entry in the same TX.

    Re-snapshots ``billing_address`` (the vendor may have edited it
    since draft creation), stamps ``issued_at = now()`` and ``due_at =
    issued_at + vendor.payment_terms_days``, posts the AP/Expense/Tax
    JE, stores ``posting_journal_entry_id`` on the bill row, and emits
    ``ap.BillIssued`` + ``ap.BillPosted``.

    Posting math
    ------------
    * Cr AP account = ``total_amount``.
    * Dr per-line expense = ``line.extended_amount``.
    * Dr tax expense = ``tax_amount`` (when > 0).

    Discount handling: when ``discount_amount > 0`` the entry would be
    unbalanced (Dr legs sum to subtotal + tax; Cr AP = subtotal -
    discount + tax). v2 of the bills system rejects bills with discount
    > 0 until Phase 9 lands a purchase-discounts-earned account.
    """
    bill = await _load(session, bill_id)
    _ensure_transition(bill.state, BillState.ISSUED)

    vendor = await _load_vendor(session, bill.vendor_id)

    # Re-snapshot billing.
    bill.billing_address_snapshot = (
        dict(vendor.billing_address) if vendor.billing_address is not None else None
    )

    issued_at = datetime.now(UTC)
    bill.issued_at = issued_at
    if vendor.payment_terms_days is not None:
        bill.due_at = issued_at + timedelta(days=vendor.payment_terms_days)

    bill.state = BillState.ISSUED

    discount_amount = _q(bill.discount_amount)
    if discount_amount > _ZERO:
        raise BillServiceError(
            f"bill {bill.bill_number} has discount_amount={discount_amount}; "
            "v2 does not post bills with discounts (Phase 9 will add a "
            "purchase-discounts-earned account)"
        )

    # Resolve accounts BEFORE building the JE so a missing setting raises
    # before we touch anything else.
    ap_account_id = await _resolve_ap_account(session, vendor=vendor)
    per_line_expense_ids: list[uuid.UUID] = []
    for line in sorted(bill.items, key=lambda i: i.line_number):
        per_line_expense_ids.append(
            await _resolve_expense_account(session, line=line, vendor=vendor)
        )

    tax_amount = _q(bill.tax_amount)
    tax_expense_account_id: uuid.UUID | None = None
    if tax_amount > _ZERO:
        tax_expense_account_id = await _resolve_tax_expense_account(session)

    total_amount = _q(bill.total_amount)

    # Build journal entry: Dr Expense (per line), Dr Tax Expense (if tax > 0),
    # Cr AP (total).
    lines_in: list[journal_service.JournalLineInput] = []
    line_no = 0

    def _next_line_no() -> int:
        nonlocal line_no
        line_no += 1
        return line_no

    for line, expense_account_id in zip(
        sorted(bill.items, key=lambda i: i.line_number),
        per_line_expense_ids,
        strict=True,
    ):
        ext = _q(line.extended_amount)
        if ext <= _ZERO:
            continue
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=expense_account_id,
                debit=ext,
                credit=_ZERO,
                line_number=_next_line_no(),
                memo=f"Expense for bill {bill.bill_number} line {line.line_number}",
            )
        )

    if tax_amount > _ZERO and tax_expense_account_id is not None:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=tax_expense_account_id,
                debit=tax_amount,
                credit=_ZERO,
                line_number=_next_line_no(),
                memo=f"Tax expense for bill {bill.bill_number}",
            )
        )

    if total_amount > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=ap_account_id,
                debit=_ZERO,
                credit=total_amount,
                line_number=_next_line_no(),
                memo=f"AP for bill {bill.bill_number}",
            )
        )

    if len(lines_in) < 2:
        raise BillServiceError(f"bill {bill.bill_number} has nothing to post (total is zero)")

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Bill {bill.bill_number}: issuance",
            posted_at=issued_at,
            lines=lines_in,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    bill.posting_journal_entry_id = entry.id
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_ISSUED,
        aggregate_id=bill.id,
        payload={
            "bill_id": str(bill.id),
            "bill_number": bill.bill_number,
            "vendor_id": str(bill.vendor_id),
            "total_amount": str(total_amount),
            "issued_at": issued_at.isoformat(),
            "due_at": bill.due_at.isoformat() if bill.due_at else None,
            "journal_entry_id": str(entry.id),
        },
        actor_user_id=actor_user_id,
    )
    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_POSTED,
        aggregate_id=bill.id,
        payload={
            "bill_id": str(bill.id),
            "bill_number": bill.bill_number,
            "journal_entry_id": str(entry.id),
            "total_amount": str(total_amount),
        },
        actor_user_id=actor_user_id,
    )
    return bill


async def void(
    session: AsyncSession,
    *,
    bill_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Bill:
    """Void a bill; reverse the posted JE (same TX).

    Only from ``issued`` / ``partially_paid`` / ``overdue`` — voiding a
    fully paid bill is illegal. If ``amount_paid > 0`` we raise
    ``BillHasPaymentsError`` (Phase 8.3 lands the unapply flow).
    """
    bill = await _load(session, bill_id)
    _ensure_transition(bill.state, BillState.VOID)

    if _q(bill.amount_paid) > _ZERO:
        raise BillHasPaymentsError(
            f"bill {bill.bill_number} has applied payments "
            f"(amount_paid={bill.amount_paid}); unapply via Phase 8.3 before voiding"
        )

    reversing_je_id: uuid.UUID | None = None
    original_je_id = bill.posting_journal_entry_id
    if original_je_id is not None:
        reversal = await journal_service.reverse(
            original_je_id,
            session=session,
            actor_user_id=actor_user_id,
            description=f"Reversal of bill {bill.bill_number}",
        )
        reversing_je_id = reversal.id

    bill.state = BillState.VOID
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_VOIDED,
        aggregate_id=bill.id,
        payload={
            "bill_id": str(bill.id),
            "bill_number": bill.bill_number,
            "vendor_id": str(bill.vendor_id),
        },
        actor_user_id=actor_user_id,
    )
    if reversing_je_id is not None and original_je_id is not None:
        await _emit(
            session,
            event_type=ap_events.TYPE_BILL_REVERSED,
            aggregate_id=bill.id,
            payload={
                "bill_id": str(bill.id),
                "bill_number": bill.bill_number,
                "reversing_journal_entry_id": str(reversing_je_id),
                "original_journal_entry_id": str(original_je_id),
            },
            actor_user_id=actor_user_id,
        )
    return bill


# ---------------------------------------------------------------------------
# Read APIs
# ---------------------------------------------------------------------------


async def get(
    session: AsyncSession,
    bill_id: uuid.UUID,
    *,
    with_items: bool = True,
) -> Bill:
    return await _load(session, bill_id, with_items=with_items)


@dataclass
class BillPage:
    items: list[Bill]
    next_cursor: str | None


async def list_bills(
    session: AsyncSession,
    *,
    state: str | None = None,
    vendor_id: uuid.UUID | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    overdue: bool | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> BillPage:
    stmt = select(Bill).options(selectinload(Bill.items))
    if state is not None:
        try:
            stmt = stmt.where(Bill.state == BillState(state))
        except ValueError as exc:
            raise BillServiceError(f"invalid state filter: {state!r}") from exc
    if vendor_id is not None:
        stmt = stmt.where(Bill.vendor_id == vendor_id)
    if due_from is not None:
        stmt = stmt.where(Bill.due_at >= due_from)
    if due_to is not None:
        stmt = stmt.where(Bill.due_at <= due_to)
    if overdue is True:
        now = datetime.now(UTC)
        stmt = stmt.where(
            and_(
                Bill.due_at < now,
                Bill.state.in_([BillState.ISSUED, BillState.PARTIALLY_PAID, BillState.OVERDUE]),
            )
        )
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Bill.bill_number.ilike(like), Bill.vendor_invoice_number.ilike(like)))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Bill.created_at < anchor_ts,
                and_(Bill.created_at == anchor_ts, Bill.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Bill.created_at), desc(Bill.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return BillPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "BillHasPaymentsError",
    "BillNotFoundError",
    "BillPage",
    "BillServiceError",
    "InvalidBillItemError",
    "InvalidBillStateError",
    "InvalidCursorError",
    "MissingApPostingAccountError",
    "VendorNotFoundForBillError",
    "create_draft",
    "get",
    "issue",
    "list_bills",
    "update_draft",
    "void",
]
