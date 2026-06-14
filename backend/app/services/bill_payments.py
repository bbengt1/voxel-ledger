"""Bill payments service (Phase 8.3, #130).

The direct AP mirror of Phase 7.4 AR payments. ``record_payment`` lands
a payment + applications atomically: validates everything, writes the
``bill_payment`` row, writes ``bill_payment_application`` rows, updates
each touched bill's ``amount_paid`` / ``amount_outstanding`` / state,
and enqueues a native QBO BillPayment via the sync outbox (QBO is the
sole ledger — epic #312, Phase 5e) — all inside the SAME DB
transaction. The same-TX invariant is the keystone v2 rule.

State machine
-------------
``pending`` -> ``posted``  (auto on record when sum(apps) == amount)
``pending`` -> ``cancelled``
``posted`` -> ``pending``      (unapply; bookkeeper only)
``posted`` -> ``bounced``      (bounce; bookkeeper only)
``posted`` -> ``cancelled``    (cancel enqueues the QBO void + flips state)
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
from app.models.vendor import Vendor, VendorState
from app.models.withholding_profile import WithholdingProfile
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import withholding as withholding_service
from app.services.bills import MissingApPostingAccountError
from app.services.reference_number import ReferenceNumberService

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
    withhold: bool | None = None,
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

    # --- Phase 9.7 (#159): resolve withholding profile + threshold ---
    # ``withhold=False`` short-circuits regardless of vendor/setting.
    # ``withhold=True`` forces a profile to be resolved.
    # ``withhold=None`` (default) lets profile resolution decide.
    withholding_profile: WithholdingProfile | None = None
    if withhold is not False:
        withholding_profile = await withholding_service.resolve_for_vendor(session, vendor=vendor)
        if withhold is True and withholding_profile is None:
            raise BillPaymentsServiceError(
                f"withhold=true was requested but vendor {vendor.vendor_number} "
                "has no withholding profile and no default is configured"
            )
        # Threshold gate. Use YTD BEFORE this payment (occurred_at as the cap).
        if withholding_profile is not None and withholding_profile.threshold_per_year is not None:
            ytd = await withholding_service.vendor_ytd_payment_total(
                session,
                vendor_id=vendor.id,
                as_of=occurred,
            )
            if ytd < Decimal(withholding_profile.threshold_per_year):
                withholding_profile = None

    # Apply rows + bill updates (no JE yet)
    application_rows: list[tuple[Bill, Decimal, BillPaymentApplication, Decimal]] = []
    total_withheld = _ZERO
    for bill, app_amt in normalized:
        bill.amount_paid = _q(bill.amount_paid + app_amt)
        bill.amount_outstanding = _q(bill.amount_outstanding - app_amt)
        _cascade_state(bill)
        withheld_for_app = _ZERO
        if withholding_profile is not None:
            withheld_for_app = _q(app_amt * Decimal(withholding_profile.rate))
            total_withheld += withheld_for_app
        app_row = BillPaymentApplication(
            bill_payment_id=payment.id,
            bill_id=bill.id,
            amount_applied=app_amt,
            withholding_amount=withheld_for_app,
            withholding_profile_id=(
                withholding_profile.id if withholding_profile is not None else None
            ),
        )
        session.add(app_row)
        application_rows.append((bill, app_amt, app_row, withheld_for_app))
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
    await session.flush()

    # Only auto-post when applications fully cover the payment amount.
    if running_total != amt:
        # Partial-apply: leave payment in pending without posting; the
        # operator can later call unapply/cancel or top up via a future
        # endpoint.
        return await _load_payment(session, payment.id)

    # QBO is the sole ledger (epic #312, Phase 5e): enqueue via the sync outbox.
    # Bill balances/state + application rows above stay local.
    from app.services.quickbooks import outbox as qbo_outbox

    await qbo_outbox.enqueue(
        session,
        kind="bill_payment",
        local_id=payment.id,
        payload={
            "vendor_id": str(vendor.id),
            "amount": str(amt),
            "txn_date": occurred.date().isoformat(),
            "reference": payment.reference_number,
            "private_note": f"Bill payment {payment_number}",
            "applications": [{"bill_id": str(b.id), "amount": str(a)} for b, a in normalized],
        },
        op="post",
    )
    if total_withheld > _ZERO:
        # Withholding: return the withheld cash from bank into a tax
        # liability (net cash out = amt - withheld).
        await qbo_outbox.enqueue(
            session,
            kind="bill_payment_withholding",
            local_id=payment.id,
            payload={
                "lines": [
                    {"role": "bank", "posting": "debit", "amount": str(total_withheld)},
                    {
                        "role": "tax_liability",
                        "posting": "credit",
                        "amount": str(total_withheld),
                    },
                ],
                "private_note": f"Withholding on {payment_number}",
            },
            op="post",
        )
    payment.posting_journal_entry_id = None
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
            # Always None: QBO is the sole ledger (epic #312, Phase 5e).
            "journal_entry_id": None,
        },
        actor_user_id=actor_user_id,
    )

    # Phase 9.7 (#159) — per-application withholding events fire AFTER
    # the JE posts so each event can reference the live application_id.
    if withholding_profile is not None and total_withheld > _ZERO:
        for bill, _app_amt, app_row, withheld_for_app in application_rows:
            if withheld_for_app <= _ZERO:
                continue
            await _emit(
                session,
                event_type=ap_events.TYPE_BILL_PAYMENT_WITHHELD,
                aggregate_id=payment.id,
                payload={
                    "payment_id": str(payment.id),
                    "payment_number": payment_number,
                    "application_id": str(app_row.id),
                    "bill_id": str(bill.id),
                    "vendor_id": str(vendor.id),
                    "profile_id": str(withholding_profile.id),
                    "profile_code": withholding_profile.code,
                    "rate": str(withholding_profile.rate),
                    "withheld_amount": str(withheld_for_app),
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
    """Enqueue the QBO BillPayment void, drop application rows, restore
    bill state, flip payment back to ``new_state`` (default ``pending``).
    """
    payment = await _load_payment(session, bill_payment_id)
    if payment.state != BillPaymentState.POSTED:
        raise InvalidBillPaymentStateError(
            f"bill payment {payment.payment_number} is in state {payment.state.value}; "
            "only posted bill payments can be unapplied"
        )

    # QBO is the sole ledger (epic #312, Phase 5e): void the QBO BillPayment
    # we pushed (the builder finds its synced outbox row).
    from app.services.quickbooks import outbox as qbo_outbox

    await qbo_outbox.enqueue(
        session,
        kind="bill_payment",
        local_id=payment.id,
        payload={"bill_payment_id": str(payment.id)},
        op="reverse",
    )

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
            # Always None: QBO is the sole ledger (epic #312, Phase 5e).
            "reversing_journal_entry_id": None,
            "original_journal_entry_id": None,
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
    From ``posted``: enqueue the QBO void, drop applications, restore
    bills, flip state to ``cancelled``.
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
