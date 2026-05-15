"""Divisions service (Phase 4.5, #68).

Light CRUD over the ``division`` aggregate, mirroring
``app.services.inventory_locations``. Each mutation appends a typed
``accounting.Division*`` event via ``EventStore.append`` inside the same
transaction as the row write so the wildcard audit-log projection picks
it up.

A division is identified by a short ``code`` (e.g. ``3DP``, ``CONS``).
Uniqueness is enforced across active rows only — a partial unique index
allows two archived rows to share a code with a new active one.

``code`` is **NOT** editable post-create — historical journal-line
tags by ``division_id`` reference the row identity, but downstream
reports filtering by code would break if we let it drift. PATCH with a
``code`` key returns 400.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import accounting as accounting_events
from app.models.division import Division
from app.schemas.events import EventCreate
from app.services import event_store


class DivisionsServiceError(Exception):
    """Base class. Routers map to 400."""


class DivisionNotFoundError(DivisionsServiceError):
    pass


class DuplicateDivisionError(DivisionsServiceError):
    pass


class InvalidCursorError(DivisionsServiceError):
    pass


class ImmutableFieldError(DivisionsServiceError):
    """A PATCH tried to change ``code``."""


# ---------------------------------------------------------------------------
# Helpers
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
            aggregate_type=accounting_events.AGGREGATE_TYPE_DIVISION,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, division_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(division_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def _find_active_duplicate(
    session: AsyncSession,
    *,
    code: str,
    exclude_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    stmt = select(Division.id).where(Division.code == code).where(Division.is_archived.is_(False))
    if exclude_id is not None:
        stmt = stmt.where(Division.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


_EDITABLE_FIELDS = frozenset({"name"})
_IMMUTABLE_FIELDS = frozenset({"code"})


async def create(
    session: AsyncSession,
    *,
    name: str,
    code: str,
    actor_user_id: uuid.UUID | None,
) -> Division:
    name = name.strip()
    code = code.strip()
    if not name:
        raise DivisionsServiceError("name is required")
    if not code:
        raise DivisionsServiceError("code is required")

    existing = await _find_active_duplicate(session, code=code)
    if existing is not None:
        raise DuplicateDivisionError(
            f"active division with code {code!r} already exists ({existing})"
        )

    division = Division(name=name, code=code, is_archived=False)
    session.add(division)
    await session.flush()

    await _emit(
        session,
        event_type=accounting_events.TYPE_DIVISION_CREATED,
        aggregate_id=division.id,
        payload={
            "division_id": str(division.id),
            "name": division.name,
            "code": division.code,
        },
        actor_user_id=actor_user_id,
    )
    return division


async def get(session: AsyncSession, division_id: uuid.UUID) -> Division:
    row = (
        await session.execute(select(Division).where(Division.id == division_id))
    ).scalar_one_or_none()
    if row is None:
        raise DivisionNotFoundError(str(division_id))
    return row


async def update(
    session: AsyncSession,
    *,
    division_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Division:
    forbidden = _IMMUTABLE_FIELDS & set(patch.keys())
    if forbidden:
        raise ImmutableFieldError(f"these fields are not editable: {sorted(forbidden)}")

    target = await get(session, division_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field, new_value in patch.items():
        if field not in _EDITABLE_FIELDS:
            continue
        if field == "name":
            if not isinstance(new_value, str) or not new_value.strip():
                raise DivisionsServiceError("name must not be empty")
            new_value = new_value.strip()
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = current
        after[field] = new_value
        setattr(target, field, new_value)

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=accounting_events.TYPE_DIVISION_UPDATED,
        aggregate_id=target.id,
        payload={
            "division_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    division_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Division:
    target = await get(session, division_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_DIVISION_ARCHIVED,
        aggregate_id=target.id,
        payload={"division_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    division_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Division:
    target = await get(session, division_id)
    if not target.is_archived:
        return target

    existing = await _find_active_duplicate(session, code=target.code, exclude_id=target.id)
    if existing is not None:
        raise DuplicateDivisionError(
            f"cannot unarchive: another active division uses code {target.code!r}"
        )

    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=accounting_events.TYPE_DIVISION_UNARCHIVED,
        aggregate_id=target.id,
        payload={"division_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class DivisionPage:
    items: list[Division]
    next_cursor: str | None


async def list_divisions(
    session: AsyncSession,
    *,
    search: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> DivisionPage:
    stmt = select(Division)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Division.name).like(pattern),
                func.lower(Division.code).like(pattern),
            )
        )
    if is_archived is not None:
        stmt = stmt.where(Division.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Division.created_at < anchor_ts,
                and_(Division.created_at == anchor_ts, Division.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Division.created_at), desc(Division.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return DivisionPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "DivisionNotFoundError",
    "DivisionPage",
    "DivisionsServiceError",
    "DuplicateDivisionError",
    "ImmutableFieldError",
    "InvalidCursorError",
    "archive",
    "create",
    "get",
    "list_divisions",
    "unarchive",
    "update",
]
