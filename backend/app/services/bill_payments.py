"""Bill payments service (Phase 8.3, #130).

The direct AP mirror of Phase 7.4 AR payments. ``record_payment`` lands
a payment + applications atomically: validates everything, writes the
``bill_payment`` row, writes ``bill_payment_application`` rows, updates
each touched bill's ``amount_paid`` / ``amount_outstanding`` / state,
and posts the JE (Dr AP / Cr Bank) — all inside the SAME DB
transaction. The same-TX invariant is the keystone v2 rule.

GL direction (inverted from AR)
-------------------------------
* Cr Bank = total payment amount (single line).
* Dr AP per applied bill = ``amount_applied`` (one line per application).

Account resolution at posting time
----------------------------------
* Cr Bank account:
  setting ``ap.payment_method_to_account[method]`` ->
  setting ``ap.default_bank_account_id`` ->
  raise ``MissingApPostingAccountError``.
* Dr AP account per applied bill:
  ``vendor.default_ap_account_id`` ->
  setting ``ap.default_ap_account_id`` ->
  raise.

State machine
-------------
``pending`` -> ``posted``  (auto on record when sum(apps) == amount)
``pending`` -> ``cancelled``
``posted`` -> ``pending``      (unapply; bookkeeper only)
``posted`` -> ``bounced``      (bounce; bookkeeper only)
``posted`` -> ``cancelled``    (cancel reverses JE + flips state)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import ap as ap_events
from app.models.bill import Bill, BillState
from app.models.bill_payment import (
    BillPayment,
    BillPaymentApplication,
    BillPaymentMethod,
    BillPaymentState,
)
from app.models.journal_entry import JournalEntry
from app.models.vendor import Vendor, VendorState
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.bills import MissingApPostingAccountError
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BillPaymentsServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class BillPaymentNotFoundError(BillPaymentsServiceError):
    """Mapped to 404."""


class VendorNotFoundForBillPaymentError(BillPaymentsServiceError):
    pass


class VendorArchivedError(BillPaymentsServiceError):
    pass


class InvalidBillPaymentStateError(BillPaymentsServiceError):
    """Illegal transition or write-while-not-pending."""


class InvalidBillPaymentAmountError(BillPaymentsServiceError):
    pass


class BillNotFoundForApplicationError(BillPaymentsServiceError):
    pass


class OverApplicationError(BillPaymentsServiceError):
    """Applied amount exceeds bill outstanding or payment amount."""


class InvalidCursorError(BillPaymentsServiceError):
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


def _coerce_method(value: str | BillPaymentMethod) -> BillPaymentMethod:
    if isinstance(value, BillPaymentMethod):
        return value
    try:
        return BillPaymentMethod(value)
    except ValueError as exc:
        raise BillPaymentsServiceError(f"invalid bill payment method: {value!r}") from exc


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _load_payment(session: AsyncSession, payment_id: uuid.UUID) -> BillPayment:
    stmt = (
        select(BillPayment)
        .where(BillPayment.id == payment_id)
        .options(selectinload(BillPayment.applications))
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise BillPaymentNotFoundError(str(payment_id))
    return row


async def _load_vendor(session: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    row = (await session.execute(select(Vendor).where(Vendor.id == vendor_id))).scalar_one_or_none()
    if row is None:
        raise VendorNotFoundForBillPaymentError(str(vendor_id))
    return row


async def _load_bill(session: AsyncSession, bill_id: uuid.UUID) -> Bill:
    row = (await session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one_or_none()
    if row is None:
        raise BillNotFoundForApplicationError(str(bill_id))
    return row


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
    aggregate_type: str = ap_events.AGGREGATE_TYPE_BILL_PAYMENT,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Account resolution
# ---------------------------------------------------------------------------


async def _resolve_bank_account(session: AsyncSession, *, method: BillPaymentMethod) -> uuid.UUID:
    """Resolve the bank/cash account credited at posting.

    ``ap.payment_method_to_account`` (JSON map) takes precedence; falls
    through to ``ap.default_bank_account_id``. Raises
    ``MissingApPostingAccountError`` if neither resolves.
    """
    mapping = await SettingsService.get("ap.payment_method_to_account", session=session)
    if isinstance(mapping, dict):
        raw = mapping.get(method.value)
        if raw:
            if isinstance(raw, uuid.UUID):
                return raw
            try:
                return uuid.UUID(str(raw))
            except ValueError as exc:
                raise MissingApPostingAccountError(
                    f"ap.payment_method_to_account[{method.value!r}] is not a valid UUID"
                ) from exc

    default = await SettingsService.get("ap.default_bank_account_id", session=session)
    if default is not None:
        if isinstance(default, uuid.UUID):
            return default
        return uuid.UUID(str(default))

    raise MissingApPostingAccountError(
        "configure default AP posting accounts: neither "
        f"ap.payment_method_to_account[{method.value!r}] nor "
        "ap.default_bank_account_id are set (needed to credit the bank "
        "account for a bill payment)"
    )


async def _resolve_ap_account(session: AsyncSession, *, vendor: Vendor) -> uuid.UUID:
    if vendor.default_ap_account_id is not None:
        return vendor.default_ap_account_id
    default = await SettingsService.get("ap.default_ap_account_id", session=session)
    if default is not None:
        if isinstance(default, uuid.UUID):
            return default
        return uuid.UUID(str(default))
    raise MissingApPostingAccountError(
        "configure default AP posting accounts: neither "
        "vendor.default_ap_account_id nor ap.default_ap_account_id are "
        "set (needed to debit AP on a bill payment)"
    )


# ---------------------------------------------------------------------------
# Bill state cascade
# ---------------------------------------------------------------------------


def _cascade_state(bill: Bill) -> None:
    """Recompute bill state from outstanding/paid after an application.

    Only moves bills that are in issued/partially_paid/overdue — never
    overrides void/paid (paid is final; void is exclusive). When fully
    paid we set ``paid``; when partially paid we land on
    ``partially_paid`` (preserves ``overdue`` only if outstanding > 0
    and the bill was already overdue — note: ``overdue`` reads as a
    snapshot taken by Phase 8.x late-fee worker; we don't proactively
    flip back to overdue here).
    """
    outstanding = _q(bill.amount_outstanding)
    paid = _q(bill.amount_paid)
    if bill.state in (BillState.PAID, BillState.VOID, BillState.DRAFT):
        return
    if outstanding <= _ZERO:
        bill.state = BillState.PAID
        return
    # If still outstanding and there's any payment, flip to partially_paid
    # (unless already overdue, in which case stay overdue).
    if paid > _ZERO and bill.state != BillState.OVERDUE:
        bill.state = BillState.PARTIALLY_PAID


# ---------------------------------------------------------------------------
# record_payment (one-shot: record + apply + post)
# ---------------------------------------------------------------------------


async def record_payment(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    method: str | BillPaymentMethod,
    amount: Decimal | str | int | float,
    occurred_at: datetime | None = None,
    reference_number: str | None = None,
    notes: str | None = None,
    applications: list[tuple[uuid.UUID, Decimal | str]] | None = None,
    actor_user_id: uuid.UUID,
) -> BillPayment:
    """Record a bill payment and (when applications cover the full amount)
    auto-post it in the same TX.

    See module docstring for state-machine + posting rules.
    """
    vendor = await _load_vendor(session, vendor_id)
    if vendor.state == VendorState.ARCHIVED:
        raise VendorArchivedError(
            f"vendor {vendor.vendor_number} is archived; cannot record bill payments"
        )

    amt = _q(amount)
    if amt <= _ZERO:
        raise InvalidBillPaymentAmountError("bill payment amount must be > 0")

    method_enum = _coerce_method(method)
    applications = applications or []

    # Validate applications up front so any error rolls back before any
    # JE work.
    normalized: list[tuple[Bill, Decimal]] = []
    running_total = _ZERO
    seen_bill_ids: set[uuid.UUID] = set()
    for bill_id, raw_amt in applications:
        if bill_id in seen_bill_ids:
            raise BillPaymentsServiceError(
                f"duplicate application for bill {bill_id} in a single payment"
            )
        seen_bill_ids.add(bill_id)
        app_amt = _q(raw_amt)
        if app_amt <= _ZERO:
            raise InvalidBillPaymentAmountError(
                f"application amount_applied must be > 0 (bill {bill_id})"
            )
        bill = await _load_bill(session, bill_id)
        if bill.vendor_id != vendor.id:
            raise BillPaymentsServiceError(f"bill {bill.bill_number} belongs to a different vendor")
        if bill.state not in (
            BillState.ISSUED,
            BillState.PARTIALLY_PAID,
            BillState.OVERDUE,
        ):
            raise InvalidBillPaymentStateError(
                f"cannot apply to bill {bill.bill_number} in state {bill.state.value}"
            )
        outstanding = _q(bill.amount_outstanding)
        if app_amt > outstanding:
            raise OverApplicationError(
                f"application of {app_amt} exceeds bill {bill.bill_number} "
                f"outstanding {outstanding}"
            )
        running_total += app_amt
        normalized.append((bill, app_amt))

    if running_total > amt:
        raise OverApplicationError(
            f"total applications {running_total} exceed payment amount {amt}"
        )

    payment_number = await ReferenceNumberService.allocate("BP", session=session)
    occurred = occurred_at or datetime.now(UTC)

    payment = BillPayment(
        payment_number=payment_number,
        vendor_id=vendor.id,
        method=method_enum,
        amount=amt,
        occurred_at=occurred,
        reference_number=reference_number,
        notes=notes,
        state=BillPaymentState.PENDING,
        created_by_user_id=actor_user_id,
    )
    session.add(payment)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise BillPaymentsServiceError(f"bill payment integrity violation: {exc.orig}") from exc

    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_PAYMENT_RECORDED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment_number,
            "vendor_id": str(vendor.id),
            "method": method_enum.value,
            "reference_number": reference_number,
            "amount": str(amt),
            "occurred_at": occurred.isoformat(),
            "state": payment.state.value,
            "notes": notes,
        },
        actor_user_id=actor_user_id,
    )

    # If there are no applications, we leave the payment in pending and
    # return. The operator can cancel or call a future /apply endpoint.
    if not normalized:
        return await _load_payment(session, payment.id)

    # Apply rows + bill updates (no JE yet)
    for bill, app_amt in normalized:
        bill.amount_paid = _q(bill.amount_paid + app_amt)
        bill.amount_outstanding = _q(bill.amount_outstanding - app_amt)
        _cascade_state(bill)
        session.add(
            BillPaymentApplication(
                bill_payment_id=payment.id,
                bill_id=bill.id,
                amount_applied=app_amt,
            )
        )
        await _emit(
            session,
            event_type=ap_events.TYPE_BILL_PAYMENT_APPLIED,
            aggregate_id=payment.id,
            payload={
                "payment_id": str(payment.id),
                "payment_number": payment_number,
                "vendor_id": str(vendor.id),
                "bill_id": str(bill.id),
                "bill_number": bill.bill_number,
                "amount_applied": str(app_amt),
            },
            actor_user_id=actor_user_id,
        )

    # Only auto-post when applications fully cover the payment amount.
    if running_total != amt:
        # Partial-apply: leave payment in pending without posting; the
        # operator can later call unapply/cancel or top up via a future
        # endpoint.
        return await _load_payment(session, payment.id)

    bank_account_id = await _resolve_bank_account(session, method=method_enum)

    lines_in: list[journal_service.JournalLineInput] = []
    line_no = 0
    for bill, app_amt in normalized:
        line_no += 1
        ap_account_id = await _resolve_ap_account(session, vendor=vendor)
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=ap_account_id,
                debit=app_amt,
                credit=_ZERO,
                line_number=line_no,
                memo=f"Apply {payment_number} to {bill.bill_number}",
            )
        )

    line_no += 1
    lines_in.append(
        journal_service.JournalLineInput(
            account_id=bank_account_id,
            debit=_ZERO,
            credit=amt,
            line_number=line_no,
            memo=f"Bill payment {payment_number} ({method_enum.value})",
        )
    )

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Bill payment {payment_number}",
            posted_at=occurred,
            lines=lines_in,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    payment.posting_journal_entry_id = entry.id
    payment.state = BillPaymentState.POSTED
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_PAYMENT_POSTED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment_number,
            "vendor_id": str(vendor.id),
            "amount": str(amt),
            "method": method_enum.value,
            "journal_entry_id": str(entry.id),
        },
        actor_user_id=actor_user_id,
    )

    return await _load_payment(session, payment.id)


# ---------------------------------------------------------------------------
# unapply / bounce / cancel
# ---------------------------------------------------------------------------


async def _restore_bills(session: AsyncSession, *, payment: BillPayment) -> None:
    """Reverse the bill cascade for every application row."""
    rows = list(payment.applications)
    for app_row in rows:
        bill = await _load_bill(session, app_row.bill_id)
        amt = _q(app_row.amount_applied)
        bill.amount_paid = _q(bill.amount_paid - amt)
        bill.amount_outstanding = _q(bill.amount_outstanding + amt)
        # Reset state based on new outstanding/paid math.
        if bill.amount_paid <= _ZERO and bill.state in (
            BillState.PARTIALLY_PAID,
            BillState.PAID,
        ):
            bill.state = BillState.ISSUED
        elif bill.state == BillState.PAID and bill.amount_outstanding > _ZERO:
            bill.state = BillState.PARTIALLY_PAID
    # Detach from the collection (cascade='all, delete-orphan' deletes them
    # at flush time). Clearing the collection first is more reliable than
    # individual session.delete() calls when reloading the parent in the
    # same TX.
    payment.applications.clear()
    await session.flush()


async def unapply(
    session: AsyncSession,
    *,
    bill_payment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    new_state: BillPaymentState = BillPaymentState.PENDING,
) -> BillPayment:
    """Reverse the JE, drop application rows, restore bill state, flip
    payment back to ``new_state`` (default ``pending``).
    """
    payment = await _load_payment(session, bill_payment_id)
    if payment.state != BillPaymentState.POSTED:
        raise InvalidBillPaymentStateError(
            f"bill payment {payment.payment_number} is in state {payment.state.value}; "
            "only posted bill payments can be unapplied"
        )

    reversing_je_id: uuid.UUID | None = None
    original_je_id = payment.posting_journal_entry_id
    if original_je_id is not None:
        reversal = await journal_service.reverse(
            original_je_id,
            session=session,
            actor_user_id=actor_user_id,
            description=f"Reversal of bill payment {payment.payment_number}",
        )
        reversing_je_id = reversal.id

    await _restore_bills(session, payment=payment)

    payment.state = new_state
    payment.posting_journal_entry_id = None
    await session.flush()

    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_PAYMENT_UNAPPLIED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "vendor_id": str(payment.vendor_id),
            "reversing_journal_entry_id": (str(reversing_je_id) if reversing_je_id else None),
            "original_journal_entry_id": (str(original_je_id) if original_je_id else None),
        },
        actor_user_id=actor_user_id,
    )
    return await _load_payment(session, payment.id)


async def bounce(
    session: AsyncSession,
    *,
    bill_payment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> BillPayment:
    """Unapply + state -> bounced. Only valid from ``posted``."""
    payment = await unapply(
        session,
        bill_payment_id=bill_payment_id,
        actor_user_id=actor_user_id,
        new_state=BillPaymentState.BOUNCED,
    )
    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_PAYMENT_BOUNCED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "vendor_id": str(payment.vendor_id),
        },
        actor_user_id=actor_user_id,
    )
    return payment


async def cancel(
    session: AsyncSession,
    *,
    bill_payment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> BillPayment:
    """Cancel a pending or posted bill payment.

    From ``pending``: just flip state.
    From ``posted``: reverse JE, drop applications, restore bills, flip
    state to ``cancelled``.
    """
    payment = await _load_payment(session, bill_payment_id)
    if payment.state == BillPaymentState.POSTED:
        payment = await unapply(
            session,
            bill_payment_id=bill_payment_id,
            actor_user_id=actor_user_id,
            new_state=BillPaymentState.CANCELLED,
        )
        await _emit(
            session,
            event_type=ap_events.TYPE_BILL_PAYMENT_CANCELLED,
            aggregate_id=payment.id,
            payload={
                "payment_id": str(payment.id),
                "payment_number": payment.payment_number,
                "vendor_id": str(payment.vendor_id),
            },
            actor_user_id=actor_user_id,
        )
        return payment

    if payment.state != BillPaymentState.PENDING:
        raise InvalidBillPaymentStateError(
            f"bill payment {payment.payment_number} cannot be cancelled "
            f"from state {payment.state.value}"
        )

    payment.state = BillPaymentState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=ap_events.TYPE_BILL_PAYMENT_CANCELLED,
        aggregate_id=payment.id,
        payload={
            "payment_id": str(payment.id),
            "payment_number": payment.payment_number,
            "vendor_id": str(payment.vendor_id),
        },
        actor_user_id=actor_user_id,
    )
    return await _load_payment(session, payment.id)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, payment_id: uuid.UUID) -> BillPayment:
    return await _load_payment(session, payment_id)


import base64  # noqa: E402
import json  # noqa: E402


def _encode_cursor(created_at: datetime, payment_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "id": str(payment_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        obj = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(obj["c"]), uuid.UUID(obj["id"])
    except Exception as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def list_bill_payments(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID | None = None,
    state: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[BillPayment], str | None]:
    stmt = select(BillPayment).options(selectinload(BillPayment.applications))
    if vendor_id is not None:
        stmt = stmt.where(BillPayment.vendor_id == vendor_id)
    if state is not None:
        try:
            stmt = stmt.where(BillPayment.state == BillPaymentState(state))
        except ValueError as exc:
            raise BillPaymentsServiceError(f"invalid state filter: {state!r}") from exc
    if date_from is not None:
        stmt = stmt.where(BillPayment.occurred_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(BillPayment.occurred_at <= date_to)

    if cursor is not None:
        cur_created, cur_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                BillPayment.created_at < cur_created,
                and_(BillPayment.created_at == cur_created, BillPayment.id < cur_id),
            )
        )

    stmt = stmt.order_by(desc(BillPayment.created_at), desc(BillPayment.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.created_at, last.id)
        rows = rows[:limit]
    return rows, next_cursor


__all__ = [
    "BillNotFoundForApplicationError",
    "BillPaymentNotFoundError",
    "BillPaymentsServiceError",
    "InvalidBillPaymentAmountError",
    "InvalidBillPaymentStateError",
    "InvalidCursorError",
    "MissingApPostingAccountError",
    "OverApplicationError",
    "VendorArchivedError",
    "VendorNotFoundForBillPaymentError",
    "bounce",
    "cancel",
    "get",
    "list_bill_payments",
    "record_payment",
    "unapply",
]
