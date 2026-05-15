"""Accounting-periods service (Phase 4.3, #66).

Periods are inclusive date ranges (``[start_date, end_date]``) with a
small open/closed/locked state machine. The non-overlap invariant is
enforced here in the service layer (always — both SQLite and PG) and
mirrored on PG by a GiST exclusion constraint installed by the
migration.

State machine
-------------
* ``open`` → ``closed`` (owner/bookkeeper)
* ``closed`` → ``open`` (owner/bookkeeper)
* ``closed`` → ``locked`` (owner only — gate enforced by the router)
* ``locked`` → * is rejected here unconditionally

Dates are immutable after create; only ``name`` is editable via
``update``.

The journal-entries service calls :func:`find_period_for` before
allocating an entry number. If no period covers the entry's posted_at
date, or the matching period is not ``open``, ``post`` raises.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting as accounting_events
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.schemas.events import EventCreate
from app.services import event_store

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AccountingPeriodsServiceError(Exception):
    """Base. Routers map to 400 unless a more specific status is appropriate."""


class AccountingPeriodNotFoundError(AccountingPeriodsServiceError):
    pass


class OverlappingPeriodError(AccountingPeriodsServiceError):
    pass


class InvalidPeriodDatesError(AccountingPeriodsServiceError):
    pass


class IllegalPeriodTransitionError(AccountingPeriodsServiceError):
    pass


class NoMatchingPeriodError(AccountingPeriodsServiceError):
    pass


class PeriodNotOpenError(AccountingPeriodsServiceError):
    pass


class InvalidCursorError(AccountingPeriodsServiceError):
    pass


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _encode_cursor(start_date: date, period_id: uuid.UUID) -> str:
    raw = json.dumps({"s": start_date.isoformat(), "i": str(period_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[date, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return date.fromisoformat(decoded["s"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


# ---------------------------------------------------------------------------
# Event emission
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
            aggregate_type=accounting_events.AGGREGATE_TYPE_ACCOUNTING_PERIOD,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Internal lookups
# ---------------------------------------------------------------------------


async def _find_overlap(
    session: AsyncSession,
    *,
    start_date: date,
    end_date: date,
    exclude_id: uuid.UUID | None = None,
) -> AccountingPeriod | None:
    # Two inclusive ranges [a1, a2] and [b1, b2] overlap iff a1 <= b2
    # AND b1 <= a2.
    stmt = select(AccountingPeriod).where(
        and_(
            AccountingPeriod.start_date <= end_date,
            AccountingPeriod.end_date >= start_date,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(AccountingPeriod.id != exclude_id)
    return (await session.execute(stmt)).scalars().first()


# ---------------------------------------------------------------------------
# CRUD + state transitions
# ---------------------------------------------------------------------------


async def create(
    name: str,
    start_date: date,
    end_date: date,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
) -> AccountingPeriod:
    name = (name or "").strip()
    if not name:
        raise AccountingPeriodsServiceError("name is required")
    if end_date < start_date:
        raise InvalidPeriodDatesError(
            f"end_date ({end_date.isoformat()}) must be on or after "
            f"start_date ({start_date.isoformat()})"
        )

    existing = await _find_overlap(session, start_date=start_date, end_date=end_date)
    if existing is not None:
        raise OverlappingPeriodError(
            f"period {existing.name!r} ({existing.start_date.isoformat()}.."
            f"{existing.end_date.isoformat()}) overlaps the requested range"
        )

    period = AccountingPeriod(
        id=uuid.uuid4(),
        name=name,
        start_date=start_date,
        end_date=end_date,
        state=AccountingPeriodState.OPEN.value,
    )
    session.add(period)
    await session.flush()

    await _emit(
        session,
        event_type=accounting_events.TYPE_PERIOD_CREATED,
        aggregate_id=period.id,
        payload={
            "period_id": str(period.id),
            "name": period.name,
            "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
        },
        actor_user_id=actor_user_id,
    )
    return period


async def get(period_id: uuid.UUID, *, session: AsyncSession) -> AccountingPeriod:
    row = (
        await session.execute(select(AccountingPeriod).where(AccountingPeriod.id == period_id))
    ).scalar_one_or_none()
    if row is None:
        raise AccountingPeriodNotFoundError(str(period_id))
    return row


async def update(
    period_id: uuid.UUID,
    *,
    name: str | None = None,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
) -> AccountingPeriod:
    period = await get(period_id, session=session)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    if name is not None:
        name_norm = name.strip()
        if not name_norm:
            raise AccountingPeriodsServiceError("name must not be empty")
        if name_norm != period.name:
            before["name"] = period.name
            after["name"] = name_norm
            period.name = name_norm

    if not before:
        return period

    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_PERIOD_UPDATED,
        aggregate_id=period.id,
        payload={
            "period_id": str(period.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return period


async def close(
    period_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
) -> AccountingPeriod:
    period = await get(period_id, session=session)
    if period.state != AccountingPeriodState.OPEN.value:
        raise IllegalPeriodTransitionError(
            f"cannot close period in state {period.state!r}; must be 'open'"
        )
    period.state = AccountingPeriodState.CLOSED.value
    period.closed_at = datetime.now(UTC)
    period.closed_by_user_id = actor_user_id
    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_PERIOD_CLOSED,
        aggregate_id=period.id,
        payload={
            "period_id": str(period.id),
            "closed_by_user_id": str(actor_user_id) if actor_user_id is not None else None,
        },
        actor_user_id=actor_user_id,
    )
    return period


async def reopen(
    period_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
) -> AccountingPeriod:
    period = await get(period_id, session=session)
    if period.state != AccountingPeriodState.CLOSED.value:
        raise IllegalPeriodTransitionError(
            f"cannot reopen period in state {period.state!r}; must be 'closed'"
        )
    period.state = AccountingPeriodState.OPEN.value
    period.closed_at = None
    period.closed_by_user_id = None
    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_PERIOD_REOPENED,
        aggregate_id=period.id,
        payload={
            "period_id": str(period.id),
            "reopened_by_user_id": str(actor_user_id) if actor_user_id is not None else None,
        },
        actor_user_id=actor_user_id,
    )
    return period


async def lock(
    period_id: uuid.UUID,
    *,
    session: AsyncSession,
    actor_user_id: uuid.UUID | None,
) -> AccountingPeriod:
    period = await get(period_id, session=session)
    if period.state != AccountingPeriodState.CLOSED.value:
        raise IllegalPeriodTransitionError(
            f"cannot lock period in state {period.state!r}; must be 'closed' "
            f"(open periods must be closed first)"
        )
    period.state = AccountingPeriodState.LOCKED.value
    period.locked_at = datetime.now(UTC)
    period.locked_by_user_id = actor_user_id
    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_PERIOD_LOCKED,
        aggregate_id=period.id,
        payload={
            "period_id": str(period.id),
            "locked_by_user_id": str(actor_user_id) if actor_user_id is not None else None,
        },
        actor_user_id=actor_user_id,
    )
    return period


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


async def find_period_for(
    target_date: date,
    *,
    session: AsyncSession,
) -> AccountingPeriod | None:
    """Return the period covering ``target_date``, or ``None``.

    The non-overlap invariant guarantees at most one match.
    """
    stmt = select(AccountingPeriod).where(
        and_(
            AccountingPeriod.start_date <= target_date,
            AccountingPeriod.end_date >= target_date,
        )
    )
    return (await session.execute(stmt)).scalars().first()


@dataclass
class AccountingPeriodPage:
    items: list[AccountingPeriod]
    next_cursor: str | None


async def list_periods(
    *,
    session: AsyncSession,
    state: str | None = None,
    year: int | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> AccountingPeriodPage:
    stmt = select(AccountingPeriod)
    if state is not None:
        # SAEnum column handles the cast for a literal string.
        stmt = stmt.where(AccountingPeriod.state == state)
    if year is not None:
        # A period "belongs to" a year if it overlaps Jan 1..Dec 31.
        jan1 = date(year, 1, 1)
        dec31 = date(year, 12, 31)
        stmt = stmt.where(
            and_(
                AccountingPeriod.start_date <= dec31,
                AccountingPeriod.end_date >= jan1,
            )
        )
    if cursor is not None:
        anchor_start, anchor_id = _decode_cursor(cursor)
        # newest-first by start_date DESC, id DESC.
        stmt = stmt.where(
            or_(
                AccountingPeriod.start_date < anchor_start,
                and_(
                    AccountingPeriod.start_date == anchor_start,
                    AccountingPeriod.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(desc(AccountingPeriod.start_date), desc(AccountingPeriod.id)).limit(
        limit + 1
    )

    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].start_date, rows[-1].id) if (rows and has_more) else None
    return AccountingPeriodPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "AccountingPeriodNotFoundError",
    "AccountingPeriodPage",
    "AccountingPeriodsServiceError",
    "IllegalPeriodTransitionError",
    "InvalidCursorError",
    "InvalidPeriodDatesError",
    "NoMatchingPeriodError",
    "OverlappingPeriodError",
    "PeriodNotOpenError",
    "close",
    "create",
    "find_period_for",
    "get",
    "list_periods",
    "lock",
    "reopen",
    "update",
]
