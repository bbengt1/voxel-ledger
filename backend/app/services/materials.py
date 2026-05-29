"""Materials catalog service (Phase 2.1).

Every mutation appends a typed ``catalog.*`` event via
``EventStore.append`` inside the same transaction as the row write, so
the wildcard audit-log projection picks it up automatically.

Read-side caches (``current_cost_per_gram``) are NEVER set by service
code — they live behind the ``inventory.MaterialReceived`` event and
the ``material_cost`` projection. On-hand quantities (Phase 3.3) live
in ``inventory_on_hand``, populated by the ``inventory_on_hand``
projection. This module deliberately ignores both caches on
create/update.
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
from app.models.material import Material
from app.models.material_receipt import MaterialReceipt
from app.schemas.events import EventCreate
from app.services import custom_fields as cf_service
from app.services import event_store


class MaterialsServiceError(Exception):
    """Base class. Routers map to 400."""


class MaterialNotFoundError(MaterialsServiceError):
    pass


class DuplicateMaterialError(MaterialsServiceError):
    pass


class InvalidCursorError(MaterialsServiceError):
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
            aggregate_type=catalog_events.AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, material_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(material_id)}).encode("utf-8")
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
    brand: str | None,
    color: str | None,
    exclude_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Return the id of an active (non-archived) material with the same
    ``(name, brand, color)`` triple, or None. The partial unique index
    enforces this at the DB layer too — this is just a friendly pre-check
    so we can raise a typed error instead of an IntegrityError.
    """
    stmt = (
        select(Material.id)
        .where(Material.name == name)
        .where(Material.brand.is_(None) if brand is None else Material.brand == brand)
        .where(Material.color.is_(None) if color is None else Material.color == color)
        .where(Material.is_archived.is_(False))
    )
    if exclude_id is not None:
        stmt = stmt.where(Material.id != exclude_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    name: str,
    brand: str | None,
    material_type: str,
    color: str | None,
    density_g_per_cm3: Decimal | None,
    spool_weight_grams: Decimal,
    actor_user_id: uuid.UUID | None,
    low_stock_threshold_grams: Decimal | None = None,
    custom_fields: dict[str, Any] | None = None,
) -> Material:
    name = name.strip()
    brand_norm = brand.strip() if brand else None
    color_norm = color.strip() if color else None

    existing = await _find_active_duplicate(session, name=name, brand=brand_norm, color=color_norm)
    if existing is not None:
        raise DuplicateMaterialError(
            f"active material with same name/brand/color already exists ({existing})"
        )

    normalized_cf = await cf_service.validate_payload("material", custom_fields, session=session)

    material = Material(
        name=name,
        brand=brand_norm,
        material_type=material_type,
        color=color_norm,
        density_g_per_cm3=density_g_per_cm3,
        spool_weight_grams=spool_weight_grams,
        current_cost_per_gram=Decimal("0"),
        low_stock_threshold_grams=low_stock_threshold_grams,
        is_archived=False,
        custom_fields=normalized_cf,
    )
    session.add(material)
    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_MATERIAL_CREATED,
        aggregate_id=material.id,
        payload={
            "material_id": str(material.id),
            "name": material.name,
            "brand": material.brand,
            "material_type": material.material_type,
            "color": material.color,
        },
        actor_user_id=actor_user_id,
    )
    return material


async def get(session: AsyncSession, material_id: uuid.UUID) -> Material:
    stmt = select(Material).where(Material.id == material_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise MaterialNotFoundError(str(material_id))
    return row


async def get_recent_receipts(
    session: AsyncSession, material_id: uuid.UUID, *, limit: int = 10
) -> list[MaterialReceipt]:
    stmt = (
        select(MaterialReceipt)
        .where(MaterialReceipt.material_id == material_id)
        .order_by(desc(MaterialReceipt.received_at), desc(MaterialReceipt.id))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


_EDITABLE_FIELDS = (
    "name",
    "brand",
    "material_type",
    "color",
    "density_g_per_cm3",
    "spool_weight_grams",
    "low_stock_threshold_grams",
)


async def update(
    session: AsyncSession,
    *,
    material_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
    custom_fields: dict[str, Any] | None = None,
) -> Material:
    target = await get(session, material_id)

    if custom_fields is not None:
        normalized_cf = await cf_service.validate_payload(
            "material", custom_fields, session=session
        )
        target.custom_fields = normalized_cf
        # Note: custom_fields change isn't included in the before/after
        # diff today — it's a separate platform aggregate event when the
        # definitions change. The row-level write is captured here.

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        if isinstance(new_value, str):
            stripped = new_value.strip()
            # Nullable text fields collapse to None when blanked.
            new_value = None if field in ("brand", "color") and stripped == "" else stripped
        current = getattr(target, field)
        if current == new_value:
            continue
        before[field] = _decimal_to_str(current) if isinstance(current, Decimal) else current
        after[field] = _decimal_to_str(new_value) if isinstance(new_value, Decimal) else new_value
        setattr(target, field, new_value)

    if not before:
        # No-op patch.
        return target

    # Duplicate check on the (name, brand, color) triple if any of those
    # three changed.
    if any(f in before for f in ("name", "brand", "color")):
        existing = await _find_active_duplicate(
            session,
            name=target.name,
            brand=target.brand,
            color=target.color,
            exclude_id=target.id,
        )
        if existing is not None:
            raise DuplicateMaterialError("another active material has the same name/brand/color")

    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_MATERIAL_UPDATED,
        aggregate_id=target.id,
        payload={
            "material_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


async def archive(
    session: AsyncSession,
    *,
    material_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Material:
    target = await get(session, material_id)
    if target.is_archived:
        return target
    target.is_archived = True
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_MATERIAL_ARCHIVED,
        aggregate_id=target.id,
        payload={"material_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


async def unarchive(
    session: AsyncSession,
    *,
    material_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Material:
    target = await get(session, material_id)
    if not target.is_archived:
        return target

    # Re-check duplicate-active-triple before clearing the flag.
    existing = await _find_active_duplicate(
        session,
        name=target.name,
        brand=target.brand,
        color=target.color,
        exclude_id=target.id,
    )
    if existing is not None:
        raise DuplicateMaterialError(
            "cannot unarchive: another active material has the same name/brand/color"
        )

    target.is_archived = False
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_MATERIAL_UNARCHIVED,
        aggregate_id=target.id,
        payload={"material_id": str(target.id)},
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------


@dataclass
class MaterialPage:
    items: list[Material]
    next_cursor: str | None


async def list_materials(
    session: AsyncSession,
    *,
    search: str | None = None,
    is_archived: bool | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> MaterialPage:
    stmt = select(Material)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Material.name).like(pattern),
                func.lower(Material.brand).like(pattern),
                func.lower(Material.material_type).like(pattern),
                func.lower(Material.color).like(pattern),
            )
        )
    if is_archived is not None:
        stmt = stmt.where(Material.is_archived.is_(is_archived))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        # (created_at DESC, id DESC) — strictly less than the anchor.
        stmt = stmt.where(
            or_(
                Material.created_at < anchor_ts,
                and_(Material.created_at == anchor_ts, Material.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Material.created_at), desc(Material.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return MaterialPage(items=rows, next_cursor=next_cursor)


# Keep an ascending-order helper around for any future replay tooling.
__all__ = [
    "DuplicateMaterialError",
    "InvalidCursorError",
    "MaterialNotFoundError",
    "MaterialPage",
    "MaterialsServiceError",
    "archive",
    "create",
    "get",
    "get_recent_receipts",
    "list_materials",
    "unarchive",
    "update",
]
