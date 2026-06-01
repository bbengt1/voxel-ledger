"""Parts catalog service (assembly-line epic #267, Phase 1).

Mirrors the products-service pattern: every mutation appends a typed
``catalog.Part*`` event via ``EventStore.append`` in the same transaction
as the row write, so the wildcard audit-log projection picks it up.

SKU allocation: ``create`` allocates ``PART-YYYY-NNNN`` via
``ReferenceNumberService.allocate("PART", …)`` unless the caller supplies
one. ``unit_cost_cached`` is reserved for the Phase 2 rollup and is never
read or written here.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import catalog as catalog_events
from app.models.part import Part
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.reference_number import ReferenceNumberService


class PartsServiceError(Exception):
    """Base class. Routers map to 400."""


class PartNotFoundError(PartsServiceError):
    pass


class DuplicateSkuError(PartsServiceError):
    pass


class InvalidCursorError(PartsServiceError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_grams(grams: dict[uuid.UUID, Decimal] | None) -> dict[str, str]:
    return {str(k): str(v) for k, v in (grams or {}).items()}


def _serialize_printer_ids(ids: list[uuid.UUID] | None) -> list[str]:
    return [str(p) for p in (ids or [])]


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
            aggregate_type=catalog_events.PART_AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, part_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(part_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def _sku_exists(
    session: AsyncSession, sku: str, *, exclude_id: uuid.UUID | None = None
) -> bool:
    stmt = select(Part.id).where(Part.sku == sku)
    if exclude_id is not None:
        stmt = stmt.where(Part.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    name: str,
    sku: str | None = None,
    description: str | None = None,
    print_minutes: int = 0,
    setup_minutes: int = 0,
    parts_per_run: int = 1,
    print_grams_by_material: dict[uuid.UUID, Decimal] | None = None,
    assigned_printer_ids: list[uuid.UUID] | None = None,
    custom_fields: dict[str, Any] | None = None,
    actor_user_id: uuid.UUID | None,
) -> Part:
    name = name.strip()
    description_norm = description.strip() if description else None
    if description_norm == "":
        description_norm = None
    if parts_per_run <= 0:
        raise PartsServiceError("parts_per_run must be > 0")
    if print_minutes < 0 or setup_minutes < 0:
        raise PartsServiceError("print_minutes and setup_minutes must be >= 0")

    if sku is None:
        allocated_sku = await ReferenceNumberService.allocate("PART", session=session)
    else:
        allocated_sku = sku.strip()
        if await _sku_exists(session, allocated_sku):
            raise DuplicateSkuError(f"sku {allocated_sku!r} already exists")

    part = Part(
        sku=allocated_sku,
        name=name,
        description=description_norm,
        print_minutes=print_minutes,
        setup_minutes=setup_minutes,
        parts_per_run=parts_per_run,
        print_grams_by_material=_serialize_grams(print_grams_by_material),
        assigned_printer_ids=_serialize_printer_ids(assigned_printer_ids),
        unit_cost_cached=None,
        is_archived=False,
        custom_fields=dict(custom_fields or {}),
    )
    session.add(part)
    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_PART_CREATED,
        aggregate_id=part.id,
        payload={"part_id": str(part.id), "sku": part.sku, "name": part.name},
        actor_user_id=actor_user_id,
    )
    return part


async def get(session: AsyncSession, part_id: uuid.UUID) -> Part:
    row = (await session.execute(select(Part).where(Part.id == part_id))).scalar_one_or_none()
    if row is None:
        raise PartNotFoundError(str(part_id))
    return row


_EDITABLE_FIELDS = (
    "sku",
    "name",
    "description",
    "print_minutes",
    "setup_minutes",
    "parts_per_run",
    "print_grams_by_material",
    "assigned_printer_ids",
)
_NULLABLE_TEXT_FIELDS = frozenset({"description"})


async def update(
    session: AsyncSession,
    *,
    part_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
    custom_fields: dict[str, Any] | None = None,
) -> Part:
    target = await get(session, part_id)

    if custom_fields is not None:
        target.custom_fields = dict(custom_fields)

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "print_grams_by_material" and new_value is not None:
            new_value = _serialize_grams(new_value)
        elif field == "assigned_printer_ids" and new_value is not None:
            new_value = _serialize_printer_ids(new_value)
        elif isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = None if field in _NULLABLE_TEXT_FIELDS and stripped == "" else stripped

        if field == "parts_per_run" and new_value is not None and new_value <= 0:
            raise PartsServiceError("parts_per_run must be > 0")
        if field in ("print_minutes", "setup_minutes") and new_value is not None and new_value < 0:
            raise PartsServiceError(f"{field} must be >= 0")

        current = getattr(target, field)
        if current == new_value:
            continue
        if (
            field == "sku"
            and new_value is not None
            and await _sku_exists(session, new_value, exclude_id=target.id)
        ):
            raise DuplicateSkuError(f"sku {new_value!r} already exists")
        before[field] = current
        after[field] = new_value
        setattr(target, field, new_value)

    if not before:
        return target

    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_PART_UPDATED,
        aggregate_id=target.id,
        payload={"part_id": str(target.id), "before": before, "after": after},
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession, *, part_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> Part:
    target = await get(session, part_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_PART_ARCHIVED,
        aggregate_id=target.id,
        payload={"part_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession, *, part_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> Part:
    target = await get(session, part_id)
    if not target.is_archived:
        return target
    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_PART_UNARCHIVED,
        aggregate_id=target.id,
        payload={"part_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class PartPage:
    items: list[Part]
    next_cursor: str | None


async def list_parts(
    session: AsyncSession,
    *,
    search: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> PartPage:
    stmt = select(Part)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Part.name).like(pattern), func.lower(Part.sku).like(pattern))
        )
    if is_archived is not None:
        stmt = stmt.where(Part.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Part.created_at < anchor_ts,
                and_(Part.created_at == anchor_ts, Part.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Part.created_at), desc(Part.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return PartPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "DuplicateSkuError",
    "InvalidCursorError",
    "PartNotFoundError",
    "PartPage",
    "PartsServiceError",
    "archive",
    "create",
    "get",
    "list_parts",
    "unarchive",
    "update",
]
