"""Supplies catalog service (Phase 2.2).

Mirrors ``app.services.materials``: every mutation appends a typed
``catalog.Supply*`` event via ``EventStore.append`` inside the same
transaction as the row write so the wildcard audit-log projection
picks it up.

Unlike materials, supplies don't have a receipts sub-resource —
``unit_cost`` is set directly on create/update. ``on_hand`` is a
read-side cache; only the initial balance is set here. Future Phase 3
inventory transactions will own subsequent updates.
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
from app.models.supply import Supply
from app.schemas.events import EventCreate
from app.services import custom_fields as cf_service
from app.services import event_store


class SuppliesServiceError(Exception):
    """Base class. Routers map to 400."""


class SupplyNotFoundError(SuppliesServiceError):
    pass


class DuplicateSupplyError(SuppliesServiceError):
    pass


class InvalidCursorError(SuppliesServiceError):
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
            aggregate_type=catalog_events.AGGREGATE_TYPE_SUPPLY,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, supply_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(supply_id)}).encode("utf-8")
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
    name: str,
    vendor: str | None,
    exclude_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Return the id of an active (non-archived) supply with the same
    ``(name, vendor)`` pair, or None. The partial unique index enforces
    this at the DB layer; this is a friendly pre-check so we can raise a
    typed error rather than an IntegrityError.
    """
    stmt = (
        select(Supply.id)
        .where(Supply.name == name)
        .where(Supply.vendor.is_(None) if vendor is None else Supply.vendor == vendor)
        .where(Supply.is_archived.is_(False))
    )
    if exclude_id is not None:
        stmt = stmt.where(Supply.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    name: str,
    unit: str,
    unit_cost: Decimal,
    vendor: str | None,
    on_hand: Decimal,
    actor_user_id: uuid.UUID | None,
    custom_fields: dict[str, Any] | None = None,
) -> Supply:
    name = name.strip()
    unit = unit.strip()
    vendor_norm = vendor.strip() if vendor else None

    existing = await _find_active_duplicate(session, name=name, vendor=vendor_norm)
    if existing is not None:
        raise DuplicateSupplyError(
            f"active supply with same name/vendor already exists ({existing})"
        )

    normalized_cf = await cf_service.validate_payload("supply", custom_fields, session=session)

    supply = Supply(
        name=name,
        unit=unit,
        unit_cost=unit_cost,
        vendor=vendor_norm,
        on_hand=on_hand,
        is_archived=False,
        custom_fields=normalized_cf,
    )
    session.add(supply)
    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_SUPPLY_CREATED,
        aggregate_id=supply.id,
        payload={
            "supply_id": str(supply.id),
            "name": supply.name,
            "unit": supply.unit,
            "unit_cost": str(supply.unit_cost),
            "vendor": supply.vendor,
        },
        actor_user_id=actor_user_id,
    )
    return supply


async def get(session: AsyncSession, supply_id: uuid.UUID) -> Supply:
    stmt = select(Supply).where(Supply.id == supply_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SupplyNotFoundError(str(supply_id))
    return row


_EDITABLE_FIELDS = ("name", "unit", "unit_cost", "vendor")


async def update(
    session: AsyncSession,
    *,
    supply_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
    custom_fields: dict[str, Any] | None = None,
) -> Supply:
    target = await get(session, supply_id)

    if custom_fields is not None:
        target.custom_fields = await cf_service.validate_payload(
            "supply", custom_fields, session=session
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if isinstance(new_value, str):
            stripped = new_value.strip()
            new_value = None if field == "vendor" and stripped == "" else stripped
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = _decimal_to_str(current) if isinstance(current, Decimal) else current
        after[field] = _decimal_to_str(new_value) if isinstance(new_value, Decimal) else new_value
        setattr(target, field, new_value)

    if not before:
        return target

    if any(f in before for f in ("name", "vendor")):
        existing = await _find_active_duplicate(
            session,
            name=target.name,
            vendor=target.vendor,
            exclude_id=target.id,
        )
        if existing is not None:
            raise DuplicateSupplyError("another active supply has the same name/vendor")

    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_SUPPLY_UPDATED,
        aggregate_id=target.id,
        payload={
            "supply_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    supply_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Supply:
    target = await get(session, supply_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_SUPPLY_ARCHIVED,
        aggregate_id=target.id,
        payload={"supply_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    supply_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Supply:
    target = await get(session, supply_id)
    if not target.is_archived:
        return target

    existing = await _find_active_duplicate(
        session,
        name=target.name,
        vendor=target.vendor,
        exclude_id=target.id,
    )
    if existing is not None:
        raise DuplicateSupplyError(
            "cannot unarchive: another active supply has the same name/vendor"
        )

    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_SUPPLY_UNARCHIVED,
        aggregate_id=target.id,
        payload={"supply_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class SupplyPage:
    items: list[Supply]
    next_cursor: str | None


async def list_supplies(
    session: AsyncSession,
    *,
    search: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> SupplyPage:
    stmt = select(Supply)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Supply.name).like(pattern),
                func.lower(Supply.unit).like(pattern),
                func.lower(Supply.vendor).like(pattern),
            )
        )
    if is_archived is not None:
        stmt = stmt.where(Supply.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Supply.created_at < anchor_ts,
                and_(Supply.created_at == anchor_ts, Supply.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Supply.created_at), desc(Supply.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return SupplyPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "DuplicateSupplyError",
    "InvalidCursorError",
    "SuppliesServiceError",
    "SupplyNotFoundError",
    "SupplyPage",
    "archive",
    "create",
    "get",
    "list_supplies",
    "unarchive",
    "update",
]
