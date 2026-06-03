"""Low-stock alerts service (Phase 3.3, #52).

Reads the ``inventory_on_hand`` projection-maintained read model and the
catalog tables (material/supply/product) and surfaces entities whose
total on-hand has fallen below their configured threshold.

Out of scope here:
- emitting an ``inventory.LowStockCrossed`` event (Phase 3.4 / 11).
- notifications / push delivery (Phase 11).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_on_hand import INVENTORY_ENTITY_KIND_ENUM, InventoryOnHand
from app.models.material import Material
from app.models.product import Product
from app.models.supply import Supply


@dataclass
class LowStockAlertRow:
    entity_kind: str
    entity_id: uuid.UUID
    entity_name: str
    threshold: Decimal
    total_on_hand: Decimal
    deficit: Decimal


def _alias_query(entity_kind: str, model, name_col, threshold_col):
    """Build a sub-select: (entity_kind literal, id, name, threshold)
    for one of the catalog models, filtered to non-archived rows with a
    configured threshold.

    ``entity_kind`` is typed as the ``inventory_entity_kind`` enum so the
    subsequent join against ``inventory_on_hand.entity_kind`` succeeds on
    Postgres without an implicit varchar→enum cast (which PG refuses).
    """
    return (
        select(
            literal(entity_kind, type_=INVENTORY_ENTITY_KIND_ENUM).label("entity_kind"),
            model.id.label("entity_id"),
            name_col.label("entity_name"),
            threshold_col.label("threshold"),
        )
        .where(threshold_col.is_not(None))
        .where(model.is_archived.is_(False))
    )


async def list_low_stock(
    *,
    session: AsyncSession,
    entity_kind: str | None = None,
    location_id: uuid.UUID | None = None,
) -> list[LowStockAlertRow]:
    """Return materials / supplies / products whose total on-hand has
    dropped below the configured threshold.

    When ``location_id`` is provided, the on-hand total is computed for
    just that one location rather than summed across every location.
    Sorted by deficit (largest first) so the worst offenders surface at
    the top.
    """
    parts = []
    if entity_kind in (None, "material"):
        parts.append(
            _alias_query("material", Material, Material.name, Material.low_stock_threshold_grams)
        )
    if entity_kind in (None, "supply"):
        parts.append(_alias_query("supply", Supply, Supply.name, Supply.low_stock_threshold))
    if entity_kind in (None, "product"):
        parts.append(_alias_query("product", Product, Product.name, Product.low_stock_threshold))
    if not parts:
        return []

    candidates = union_all(*parts).subquery()

    on_hand_stmt = select(
        InventoryOnHand.entity_kind.label("entity_kind"),
        InventoryOnHand.entity_id.label("entity_id"),
        func.coalesce(func.sum(InventoryOnHand.on_hand), 0).label("total_on_hand"),
    )
    if location_id is not None:
        on_hand_stmt = on_hand_stmt.where(InventoryOnHand.location_id == location_id)
    on_hand_stmt = on_hand_stmt.group_by(InventoryOnHand.entity_kind, InventoryOnHand.entity_id)
    on_hand_sub = on_hand_stmt.subquery()

    joined = select(
        candidates.c.entity_kind,
        candidates.c.entity_id,
        candidates.c.entity_name,
        candidates.c.threshold,
        func.coalesce(on_hand_sub.c.total_on_hand, 0).label("total_on_hand"),
    ).select_from(
        candidates.outerjoin(
            on_hand_sub,
            (candidates.c.entity_kind == on_hand_sub.c.entity_kind)
            & (candidates.c.entity_id == on_hand_sub.c.entity_id),
        )
    )

    rows = (await session.execute(joined)).all()

    alerts: list[LowStockAlertRow] = []
    for row in rows:
        threshold = Decimal(str(row.threshold))
        total = Decimal(str(row.total_on_hand))
        if total >= threshold:
            continue
        alerts.append(
            LowStockAlertRow(
                entity_kind=row.entity_kind,
                entity_id=row.entity_id,
                entity_name=row.entity_name,
                threshold=threshold,
                total_on_hand=total,
                deficit=threshold - total,
            )
        )
    alerts.sort(key=lambda a: a.deficit, reverse=True)
    return alerts


async def on_hand_for_entity(
    *,
    session: AsyncSession,
    entity_kind: str,
    entity_id: uuid.UUID,
) -> dict[uuid.UUID, Decimal]:
    """Return the per-location on-hand map for one entity. Empty map if
    no rows exist."""
    stmt = (
        select(InventoryOnHand.location_id, InventoryOnHand.on_hand)
        .where(InventoryOnHand.entity_kind == entity_kind)
        .where(InventoryOnHand.entity_id == entity_id)
    )
    rows = (await session.execute(stmt)).all()
    return {r[0]: Decimal(str(r[1])) for r in rows}


async def total_on_hand_for_entity(
    *,
    session: AsyncSession,
    entity_kind: str,
    entity_id: uuid.UUID,
) -> Decimal:
    per_loc = await on_hand_for_entity(
        session=session, entity_kind=entity_kind, entity_id=entity_id
    )
    return sum(per_loc.values(), start=Decimal("0"))


async def total_on_hand_for_entities(
    *,
    session: AsyncSession,
    entity_kind: str,
    entity_ids: list[uuid.UUID],
) -> dict[uuid.UUID, Decimal]:
    """Bulk total-on-hand (summed across locations) for many entities of one
    kind, in a single query. Every requested id is present in the result —
    entities with no inventory rows map to ``Decimal("0")``. Use this for
    list views to avoid an N+1 of :func:`total_on_hand_for_entity`."""
    out: dict[uuid.UUID, Decimal] = {eid: Decimal("0") for eid in entity_ids}
    if not entity_ids:
        return out
    stmt = (
        select(
            InventoryOnHand.entity_id,
            func.coalesce(func.sum(InventoryOnHand.on_hand), 0),
        )
        .where(InventoryOnHand.entity_kind == entity_kind)
        .where(InventoryOnHand.entity_id.in_(entity_ids))
        .group_by(InventoryOnHand.entity_id)
    )
    for entity_id, total in (await session.execute(stmt)).all():
        out[entity_id] = Decimal(str(total))
    return out


__all__ = [
    "LowStockAlertRow",
    "list_low_stock",
    "on_hand_for_entity",
    "total_on_hand_for_entities",
    "total_on_hand_for_entity",
]
