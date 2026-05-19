"""Tax remittance service (Phase 9.6, #158).

Records an operator-initiated payment to a revenue authority against
one tax profile. The same DB transaction posts a balanced JE:

* Dr each rate's ``liability_account_id`` for that rate's slice of the
  payment (default: pay down the full per-rate outstanding balance at
  ``period_end``).
* Cr ``bank_account_id`` for the full ``amount_paid``.

By default the caller must clear the profile's entire outstanding tax
balance for the period — a partial payment is blocked unless
``allow_partial=True``, in which case the payment is allocated across
the rates proportionally to their outstanding balances.

Cancellation reverses the JE via :func:`journal_entries.reverse` and
flips the row to ``cancelled``. The original JE id is preserved on the
row alongside the reversal id in the event payload.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import tax as tax_events
from app.models.account import Account, AccountType
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.models.tax_profile import TaxProfile
from app.models.tax_remittance import (
    TaxRemittance,
    TaxRemittanceMethod,
    TaxRemittanceState,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.reference_number import ReferenceNumberService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TaxRemittanceServiceError(Exception):
    """Base. Routers map subclasses to 400 unless noted."""


class TaxRemittanceNotFoundError(TaxRemittanceServiceError):
    """Mapped to 404."""


class InvalidTaxRemittanceError(TaxRemittanceServiceError):
    """Bad input (amount, accounts, dates)."""


class TaxRemittanceStateError(TaxRemittanceServiceError):
    """Wrong state for the requested transition (e.g. cancelling twice)."""


class TaxRemittancePartialBlockedError(TaxRemittanceServiceError):
    """``amount_paid`` doesn't equal the profile's outstanding balance and
    ``allow_partial`` was not set."""


class InvalidCursorError(TaxRemittanceServiceError):
    pass


# ---------------------------------------------------------------------------
# Decimal helpers (match the Numeric(18, 6) column).
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, remittance_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(remittance_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Events
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
            aggregate_type=tax_events.AGGREGATE_TYPE_TAX_REMITTANCE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Per-rate outstanding balance computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateOutstanding:
    rate_id: uuid.UUID
    ordinal: int
    name: str
    liability_account_id: uuid.UUID
    outstanding: Decimal


async def _outstanding_per_rate(
    session: AsyncSession, *, profile: TaxProfile, as_of: date
) -> list[RateOutstanding]:
    """Per-rate balance on each liability account as of ``as_of``.

    Outstanding = sum(credits) - sum(debits) on the rate's liability account,
    summed over every journal line whose entry posted_at falls on or
    before ``as_of``. Positive numbers mean we owe; negative would mean
    we over-remitted.
    """
    as_of_dt = datetime.combine(as_of, datetime.max.time(), tzinfo=UTC)

    results: list[RateOutstanding] = []
    for rate in profile.rates:
        stmt = (
            select(
                func.coalesce(func.sum(JournalLine.credit), 0),
                func.coalesce(func.sum(JournalLine.debit), 0),
            )
            .select_from(JournalLine)
            .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
            .where(JournalLine.account_id == rate.liability_account_id)
            .where(JournalEntry.posted_at <= as_of_dt)
        )
        row = (await session.execute(stmt)).one()
        cr_sum = Decimal(str(row[0] or 0))
        dr_sum = Decimal(str(row[1] or 0))
        results.append(
            RateOutstanding(
                rate_id=rate.id,
                ordinal=rate.ordinal,
                name=rate.name,
                liability_account_id=rate.liability_account_id,
                outstanding=_q(cr_sum - dr_sum),
            )
        )
    return results


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------


async def _load_profile(session: AsyncSession, profile_id: uuid.UUID) -> TaxProfile:
    profile = (
        await session.execute(
            select(TaxProfile)
            .where(TaxProfile.id == profile_id)
            .options(selectinload(TaxProfile.rates))
        )
    ).scalar_one_or_none()
    if profile is None:
        raise InvalidTaxRemittanceError(f"tax profile not found: {profile_id}")
    return profile


async def _load_bank_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    acct = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acct is None:
        raise InvalidTaxRemittanceError(f"bank account not found: {account_id}")
    if acct.is_archived:
        raise InvalidTaxRemittanceError(f"bank account {acct.code!r} is archived")
    actual_type = acct.type.value if hasattr(acct.type, "value") else acct.type
    if actual_type != AccountType.ASSET.value:
        raise InvalidTaxRemittanceError(
            f"bank_account_id {acct.code!r} has type {actual_type!r}; expected 'asset'"
        )
    return acct


def _allocate(
    *,
    amount: Decimal,
    rates: list[RateOutstanding],
    allow_partial: bool,
) -> list[tuple[RateOutstanding, Decimal]]:
    """Return a list of ``(rate, dr_amount)`` whose Decimal sum equals
    ``amount`` exactly.

    Default (``allow_partial=False``): each rate is paid down by its
    full ``outstanding``; the caller's ``amount`` must equal Σ
    outstanding (after quantize).

    Partial (``allow_partial=True``): allocate proportionally to
    outstanding; the LAST positive rate picks up the rounding remainder
    so the sum lines up exactly.
    """
    amount = _q(amount)
    positives = [r for r in rates if r.outstanding > _ZERO]
    total_outstanding = _q(sum((r.outstanding for r in positives), _ZERO))

    if not positives or total_outstanding <= _ZERO:
        raise InvalidTaxRemittanceError(
            "profile has no outstanding tax liability for the requested period"
        )

    if not allow_partial:
        if amount != total_outstanding:
            raise TaxRemittancePartialBlockedError(
                f"amount_paid {amount} does not match outstanding "
                f"{total_outstanding}; pass allow_partial=true to record a "
                "partial payment"
            )
        return [(r, r.outstanding) for r in positives]

    if amount > total_outstanding:
        raise InvalidTaxRemittanceError(
            f"amount_paid {amount} exceeds outstanding {total_outstanding}"
        )

    out: list[tuple[RateOutstanding, Decimal]] = []
    running = _ZERO
    for i, r in enumerate(positives):
        if i == len(positives) - 1:
            piece = amount - running
        else:
            piece = _q(amount * r.outstanding / total_outstanding)
        out.append((r, piece))
        running += piece
    return out


async def record(
    *,
    session: AsyncSession,
    profile_id: uuid.UUID,
    period_start: date,
    period_end: date,
    amount_paid: Decimal | str | int | float,
    paid_on: date,
    method: str | TaxRemittanceMethod,
    bank_account_id: uuid.UUID,
    reference_number: str | None = None,
    notes: str | None = None,
    allow_partial: bool = False,
    actor_user_id: uuid.UUID,
) -> TaxRemittance:
    """Allocate + insert + post + emit, all in the same DB transaction.

    The router commits. Any raise rolls back everything (row + JE +
    event).
    """
    amount = _q(amount_paid)
    if amount <= _ZERO:
        raise InvalidTaxRemittanceError("amount_paid must be > 0")
    if period_end < period_start:
        raise InvalidTaxRemittanceError("period_end must be >= period_start")

    try:
        method_e = (
            TaxRemittanceMethod(method) if not isinstance(method, TaxRemittanceMethod) else method
        )
    except ValueError as exc:
        raise InvalidTaxRemittanceError(f"invalid method: {method!r}") from exc

    profile = await _load_profile(session, profile_id)
    if not profile.rates:
        raise InvalidTaxRemittanceError(f"tax profile {profile.code!r} has no rates configured")
    bank = await _load_bank_account(session, bank_account_id)

    per_rate = await _outstanding_per_rate(session, profile=profile, as_of=period_end)
    allocations = _allocate(amount=amount, rates=per_rate, allow_partial=allow_partial)

    # Allocate the reference number now so it's stable across the
    # same-TX inserts below.
    remittance_number = await ReferenceNumberService.allocate("TAX", session=session)

    remittance_id = uuid.uuid4()
    remittance = TaxRemittance(
        id=remittance_id,
        remittance_number=remittance_number,
        profile_id=profile.id,
        period_start=period_start,
        period_end=period_end,
        amount_paid=amount,
        paid_on=paid_on,
        method=method_e,
        reference_number=reference_number,
        bank_account_id=bank.id,
        state=TaxRemittanceState.RECORDED,
        notes=notes,
        created_by_user_id=actor_user_id,
    )
    session.add(remittance)
    await session.flush()

    posted_at = datetime.combine(paid_on, datetime.min.time(), tzinfo=UTC)
    lines: list[journal_service.JournalLineInput] = []
    line_no = 1
    per_rate_payload: list[dict[str, Any]] = []
    for r, piece in allocations:
        if piece <= _ZERO:
            continue
        lines.append(
            journal_service.JournalLineInput(
                account_id=r.liability_account_id,
                debit=piece,
                credit=_ZERO,
                line_number=line_no,
                memo=f"Dr tax liability {r.name} for {remittance_number}",
            )
        )
        line_no += 1
        per_rate_payload.append(
            {
                "rate_id": str(r.rate_id),
                "ordinal": r.ordinal,
                "name": r.name,
                "liability_account_id": str(r.liability_account_id),
                "amount": str(piece),
            }
        )
    lines.append(
        journal_service.JournalLineInput(
            account_id=bank.id,
            debit=_ZERO,
            credit=amount,
            line_number=line_no,
            memo=f"Cr bank for tax remittance {remittance_number}",
        )
    )

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Tax remittance {remittance_number} ({profile.code})",
            posted_at=posted_at,
            lines=lines,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    remittance.posting_journal_entry_id = entry.id
    await session.flush()

    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_REMITTANCE_RECORDED,
        aggregate_id=remittance.id,
        payload={
            "remittance_id": str(remittance.id),
            "remittance_number": remittance_number,
            "profile_id": str(profile.id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "amount_paid": str(amount),
            "paid_on": paid_on.isoformat(),
            "method": method_e.value,
            "reference_number": reference_number,
            "bank_account_id": str(bank.id),
            "journal_entry_id": str(entry.id),
            "per_rate_allocations": per_rate_payload,
        },
        actor_user_id=actor_user_id,
    )
    return remittance


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


async def cancel(
    *,
    session: AsyncSession,
    remittance_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> TaxRemittance:
    """Reverse the JE and flip the row to ``cancelled``.

    The original ``posting_journal_entry_id`` stays on the row; the
    reversal JE id is preserved on the event payload only.
    """
    remittance = (
        await session.execute(select(TaxRemittance).where(TaxRemittance.id == remittance_id))
    ).scalar_one_or_none()
    if remittance is None:
        raise TaxRemittanceNotFoundError(str(remittance_id))
    if remittance.state == TaxRemittanceState.CANCELLED:
        raise TaxRemittanceStateError(
            f"tax remittance {remittance.remittance_number} is already cancelled"
        )
    if remittance.posting_journal_entry_id is None:
        raise TaxRemittanceStateError(
            f"tax remittance {remittance.remittance_number} has no posted JE to reverse"
        )

    original_je_id = remittance.posting_journal_entry_id
    reversal = await journal_service.reverse(
        original_je_id,
        session=session,
        actor_user_id=actor_user_id,
        description=f"Reversal of tax remittance {remittance.remittance_number}",
    )
    remittance.state = TaxRemittanceState.CANCELLED
    await session.flush()

    await _emit(
        session,
        event_type=tax_events.TYPE_TAX_REMITTANCE_CANCELLED,
        aggregate_id=remittance.id,
        payload={
            "remittance_id": str(remittance.id),
            "remittance_number": remittance.remittance_number,
            "original_journal_entry_id": str(original_je_id),
            "reversal_journal_entry_id": str(reversal.id),
        },
        actor_user_id=actor_user_id,
    )
    return remittance


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, remittance_id: uuid.UUID) -> TaxRemittance:
    remittance = (
        await session.execute(select(TaxRemittance).where(TaxRemittance.id == remittance_id))
    ).scalar_one_or_none()
    if remittance is None:
        raise TaxRemittanceNotFoundError(str(remittance_id))
    return remittance


@dataclass
class TaxRemittancePage:
    items: list[TaxRemittance]
    next_cursor: str | None


async def list_remittances(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID | None = None,
    state: str | None = None,
    paid_from: date | None = None,
    paid_to: date | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> TaxRemittancePage:
    stmt = select(TaxRemittance)
    if profile_id is not None:
        stmt = stmt.where(TaxRemittance.profile_id == profile_id)
    if state is not None:
        try:
            stmt = stmt.where(TaxRemittance.state == TaxRemittanceState(state))
        except ValueError as exc:
            raise InvalidTaxRemittanceError(f"invalid state filter: {state!r}") from exc
    if paid_from is not None:
        stmt = stmt.where(TaxRemittance.paid_on >= paid_from)
    if paid_to is not None:
        stmt = stmt.where(TaxRemittance.paid_on <= paid_to)
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                TaxRemittance.created_at < anchor_ts,
                and_(
                    TaxRemittance.created_at == anchor_ts,
                    TaxRemittance.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(desc(TaxRemittance.created_at), desc(TaxRemittance.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return TaxRemittancePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "InvalidCursorError",
    "InvalidTaxRemittanceError",
    "RateOutstanding",
    "TaxRemittanceNotFoundError",
    "TaxRemittancePage",
    "TaxRemittancePartialBlockedError",
    "TaxRemittanceServiceError",
    "TaxRemittanceStateError",
    "cancel",
    "get",
    "list_remittances",
    "record",
]
