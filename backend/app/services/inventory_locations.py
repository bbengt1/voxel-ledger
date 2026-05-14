"""Inventory locations service (Phase 3.1).

Mirrors ``app.services.supplies``: every mutation appends a typed
``inventory.Location*`` event via ``EventStore.append`` inside the same
transaction as the row write so the wildcard audit-log projection picks
it up.

A location is identified by a short ``code`` (e.g. ``WSB``,
``FG``). Uniqueness is enforced across active rows only — a partial
unique index allows two archived rows to share a code with a new active
one. The service does a friendly pre-check before relying on the index.
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

from app.events.types import inventory as inventory_events
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.schemas.events import EventCreate
from app.services import event_store


class InventoryLocationsServiceError(Exception):
    """Base class. Routers map to 400."""


class InventoryLocationNotFoundError(InventoryLocationsServiceError):
    pass


class DuplicateInventoryLocationError(InventoryLocationsServiceError):
    pass


class InvalidCursorError(InventoryLocationsServiceError):
    pass


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
            aggregate_type=inventory_events.AGGREGATE_TYPE_INVENTORY_LOCATION,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, location_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(location_id)}).encode("utf-8")
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
    stmt = (
        select(InventoryLocation.id)
        .where(InventoryLocation.code == code)
        .where(InventoryLocation.is_archived.is_(False))
    )
    if exclude_id is not None:
        stmt = stmt.where(InventoryLocation.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _coerce_kind(kind: str | InventoryLocationKind) -> InventoryLocationKind:
    if isinstance(kind, InventoryLocationKind):
        return kind
    try:
        return InventoryLocationKind(kind)
    except ValueError as exc:
        raise InventoryLocationsServiceError(f"invalid kind: {kind!r}") from exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    name: str,
    code: str,
    kind: str | InventoryLocationKind,
    description: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> InventoryLocation:
    name = name.strip()
    code = code.strip()
    if not name:
        raise InventoryLocationsServiceError("name is required")
    if not code:
        raise InventoryLocationsServiceError("code is required")
    kind_value = _coerce_kind(kind)
    description_norm = description.strip() if description else None
    if description_norm == "":
        description_norm = None

    existing = await _find_active_duplicate(session, code=code)
    if existing is not None:
        raise DuplicateInventoryLocationError(
            f"active inventory location with code {code!r} already exists ({existing})"
        )

    location = InventoryLocation(
        name=name,
        code=code,
        kind=kind_value,
        description=description_norm,
        is_archived=False,
    )
    session.add(location)
    await session.flush()

    await _emit(
        session,
        event_type=inventory_events.TYPE_LOCATION_CREATED,
        aggregate_id=location.id,
        payload={
            "location_id": str(location.id),
            "name": location.name,
            "code": location.code,
            "kind": kind_value.value,
        },
        actor_user_id=actor_user_id,
    )
    return location


async def get(session: AsyncSession, location_id: uuid.UUID) -> InventoryLocation:
    stmt = select(InventoryLocation).where(InventoryLocation.id == location_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise InventoryLocationNotFoundError(str(location_id))
    return row


_EDITABLE_FIELDS = ("name", "code", "kind", "description")


async def update(
    session: AsyncSession,
    *,
    location_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> InventoryLocation:
    target = await get(session, location_id)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "kind" and new_value is not None:
            new_value = _coerce_kind(new_value)
        elif isinstance(new_value, str):
            stripped = new_value.strip()
            if field == "description":
                new_value = None if stripped == "" else stripped
            else:
                if not stripped:
                    raise InventoryLocationsServiceError(f"{field} must not be empty")
                new_value = stripped
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = current.value if isinstance(current, InventoryLocationKind) else current
        after[field] = (
            new_value.value if isinstance(new_value, InventoryLocationKind) else new_value
        )
        setattr(target, field, new_value)

    if not before:
        return target

    if "code" in before:
        existing = await _find_active_duplicate(session, code=target.code, exclude_id=target.id)
        if existing is not None:
            raise DuplicateInventoryLocationError(
                f"another active inventory location uses code {target.code!r}"
            )

    await session.flush()

    await _emit(
        session,
        event_type=inventory_events.TYPE_LOCATION_UPDATED,
        aggregate_id=target.id,
        payload={
            "location_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    location_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> InventoryLocation:
    target = await get(session, location_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=inventory_events.TYPE_LOCATION_ARCHIVED,
        aggregate_id=target.id,
        payload={"location_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    location_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> InventoryLocation:
    target = await get(session, location_id)
    if not target.is_archived:
        return target

    existing = await _find_active_duplicate(session, code=target.code, exclude_id=target.id)
    if existing is not None:
        raise DuplicateInventoryLocationError(
            f"cannot unarchive: another active inventory location uses code {target.code!r}"
        )

    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=inventory_events.TYPE_LOCATION_UNARCHIVED,
        aggregate_id=target.id,
        payload={"location_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class InventoryLocationPage:
    items: list[InventoryLocation]
    next_cursor: str | None


async def list_locations(
    session: AsyncSession,
    *,
    search: str | None = None,
    kind: str | InventoryLocationKind | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> InventoryLocationPage:
    stmt = select(InventoryLocation)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(InventoryLocation.name).like(pattern),
                func.lower(InventoryLocation.code).like(pattern),
            )
        )
    if kind is not None:
        stmt = stmt.where(InventoryLocation.kind == _coerce_kind(kind))
    if is_archived is not None:
        stmt = stmt.where(InventoryLocation.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                InventoryLocation.created_at < anchor_ts,
                and_(
                    InventoryLocation.created_at == anchor_ts,
                    InventoryLocation.id < anchor_id,
                ),
            )
        )
    stmt = stmt.order_by(desc(InventoryLocation.created_at), desc(InventoryLocation.id)).limit(
        limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return InventoryLocationPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "DuplicateInventoryLocationError",
    "InvalidCursorError",
    "InventoryLocationNotFoundError",
    "InventoryLocationPage",
    "InventoryLocationsServiceError",
    "archive",
    "create",
    "get",
    "list_locations",
    "unarchive",
    "update",
]
