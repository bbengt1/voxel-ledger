"""Rates catalog service (Phase 2.2).

Rates capture per-hour labor and machine costs, and overhead as a
decimal percentage. Every mutation emits a typed ``catalog.Rate*``
event via ``EventStore.append`` inside the same transaction as the row
write, matching the materials/supplies pattern.

A future Phase 5 cost calculator will resolve rates with this fallback chain:
  1. If a Rate row is marked `is_default_for_kind` for the requested kind, use its value.
  2. Otherwise, fall back to the corresponding setting in #25's registry
     (e.g. `cost_engine.labor_rate_per_hour` for kind=labor).
This issue ships step 1; the fallback wiring lands with the cost engine.

The partial unique index ``ux_rate_default_per_kind`` (kind WHERE
is_default_for_kind = true) enforces "at most one default per kind" at
the DB level. ``set_default`` performs the unflag-old / flag-new
sequence inside a single transaction so the index constraint is never
violated mid-write.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import catalog as catalog_events
from app.models.rate import Rate, RateKind
from app.schemas.events import EventCreate
from app.services import event_store


class RatesServiceError(Exception):
    """Base class. Routers map to 400."""


class RateNotFoundError(RatesServiceError):
    pass


class InvalidCursorError(RatesServiceError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decimal_to_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


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
            aggregate_type=catalog_events.AGGREGATE_TYPE_RATE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, rate_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(rate_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def _current_default_for_kind(
    session: AsyncSession, kind: RateKind, *, exclude_id: uuid.UUID | None = None
) -> Rate | None:
    stmt = select(Rate).where(Rate.kind == kind).where(Rate.is_default_for_kind.is_(True))
    if exclude_id is not None:
        stmt = stmt.where(Rate.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    name: str,
    kind: RateKind,
    value: Decimal,
    applies_to_printer_id: uuid.UUID | None,
    is_default_for_kind: bool,
    actor_user_id: uuid.UUID | None,
) -> Rate:
    name = name.strip()

    # If the caller asked us to default this new row, atomically unflag
    # any prior default for the same kind first so the partial unique
    # index is never violated.
    previous_default: Rate | None = None
    if is_default_for_kind:
        previous_default = await _current_default_for_kind(session, kind)
        if previous_default is not None:
            previous_default.is_default_for_kind = False
            await session.flush()

    rate = Rate(
        name=name,
        kind=kind,
        value=value,
        applies_to_printer_id=applies_to_printer_id,
        is_default_for_kind=is_default_for_kind,
        is_archived=False,
    )
    session.add(rate)
    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_RATE_CREATED,
        aggregate_id=rate.id,
        payload={
            "rate_id": str(rate.id),
            "name": rate.name,
            "kind": rate.kind.value,
            "value": str(rate.value),
            "is_default_for_kind": rate.is_default_for_kind,
        },
        actor_user_id=actor_user_id,
    )

    if is_default_for_kind:
        await _emit(
            session,
            event_type=catalog_events.TYPE_RATE_DEFAULTED,
            aggregate_id=rate.id,
            payload={
                "rate_id": str(rate.id),
                "kind": rate.kind.value,
                "previous_default_rate_id": (
                    str(previous_default.id) if previous_default is not None else None
                ),
            },
            actor_user_id=actor_user_id,
        )

    return rate


async def get(session: AsyncSession, rate_id: uuid.UUID) -> Rate:
    stmt = select(Rate).where(Rate.id == rate_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise RateNotFoundError(str(rate_id))
    return row


_EDITABLE_FIELDS = ("name", "value", "applies_to_printer_id")


async def update(
    session: AsyncSession,
    *,
    rate_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Rate:
    target = await get(session, rate_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if isinstance(new_value, str):
            new_value = new_value.strip()
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = (
            _decimal_to_str(current)
            if isinstance(current, Decimal)
            else (str(current) if isinstance(current, uuid.UUID) else current)
        )
        after[field] = (
            _decimal_to_str(new_value)
            if isinstance(new_value, Decimal)
            else (str(new_value) if isinstance(new_value, uuid.UUID) else new_value)
        )
        setattr(target, field, new_value)

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_RATE_UPDATED,
        aggregate_id=target.id,
        payload={
            "rate_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def set_default(
    session: AsyncSession,
    *,
    rate_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Rate:
    """Make ``rate_id`` the default for its kind atomically.

    Steps inside a single transaction:
      1. Unflag the prior default for the same kind (if any).
      2. Flag the new default.
      3. Emit ``catalog.RateDefaulted`` with the previous id.

    The partial unique index on ``(kind) WHERE is_default_for_kind =
    true`` is the DB-level enforcement that backstops this sequence.
    """
    target = await get(session, rate_id)
    if target.is_archived:
        raise RatesServiceError("cannot set an archived rate as the default")

    previous_default = await _current_default_for_kind(session, target.kind, exclude_id=target.id)

    if previous_default is not None:
        previous_default.is_default_for_kind = False
        await session.flush()

    if not target.is_default_for_kind:
        target.is_default_for_kind = True
        await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_RATE_DEFAULTED,
        aggregate_id=target.id,
        payload={
            "rate_id": str(target.id),
            "kind": target.kind.value,
            "previous_default_rate_id": (
                str(previous_default.id) if previous_default is not None else None
            ),
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    rate_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Rate:
    target = await get(session, rate_id)
    if target.is_archived:
        return target
    # Archiving clears the default flag — an archived rate can't be the
    # active default. This keeps the partial unique index clean.
    target.is_archived = True
    target.is_default_for_kind = False
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_RATE_ARCHIVED,
        aggregate_id=target.id,
        payload={"rate_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    rate_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Rate:
    target = await get(session, rate_id)
    if not target.is_archived:
        return target
    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_RATE_UNARCHIVED,
        aggregate_id=target.id,
        payload={"rate_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class RatePage:
    items: list[Rate]
    next_cursor: str | None


async def list_rates(
    session: AsyncSession,
    *,
    kind: RateKind | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> RatePage:
    stmt = select(Rate)
    if kind is not None:
        stmt = stmt.where(Rate.kind == kind)
    if is_archived is not None:
        stmt = stmt.where(Rate.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Rate.created_at < anchor_ts,
                and_(Rate.created_at == anchor_ts, Rate.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Rate.created_at), desc(Rate.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return RatePage(items=rows, next_cursor=next_cursor)


__all__ = [
    "InvalidCursorError",
    "RateNotFoundError",
    "RatePage",
    "RatesServiceError",
    "archive",
    "create",
    "get",
    "list_rates",
    "set_default",
    "unarchive",
    "update",
]
