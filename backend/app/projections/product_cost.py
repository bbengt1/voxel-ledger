"""Projection: roll up ``product.unit_cost_cached`` from the BOM tree.

This projection subscribes to multiple event types:

* ``catalog.BomComponentAdded``
* ``catalog.BomComponentRemoved``
* ``catalog.BomComponentQuantityChanged``
* ``inventory.MaterialReceived`` (material cost-per-gram changed)
* ``catalog.SupplyUpdated`` (supply unit_cost may have changed)
* ``catalog.ProductCostChanged`` (a sub-product's cost changed —
  propagate to ancestors)

For each event we compute the set of "affected products" — products
whose cached cost may need recomputation — then call
:func:`app.services.bom.compute_cost_tree` for each and write back the
new ``unit_cost_cached``. When a value actually changes (including
to/from NULL) we emit ``catalog.ProductCostChanged`` so the projection
itself sees the change on a subsequent live append and propagates it up
the tree.

Yes, the projection emits its own events. That's allowed: the emit
happens inside the same session, and ``EventStore.append`` will dispatch
the new event through every registered handler — including this one —
synchronously. The recursion terminates because we only emit when the
cached value actually changes, and the cost-tree walk is bounded by
``BomService.DEFAULT_MAX_DEPTH``.

``ProductPriceChanged`` is intentionally NOT subscribed: that event
represents sales price (an input), not cached cost (a derived value).

Registered under several handler names (one per event_type), all
sharing the same underlying logic. The replay engine processes each
handler independently.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import catalog as catalog_events
from app.events.types import inventory as inventory_events
from app.models.event import Event
from app.models.product import Product
from app.models.product_bom_item import (
    COMPONENT_KIND_MATERIAL,
    COMPONENT_KIND_PART,
    COMPONENT_KIND_SUPPLY,
)
from app.projections.registry import projection
from app.schemas.events import EventCreate
from app.services import bom as bom_service
from app.services import event_store

log = logging.getLogger(__name__)

READ_MODEL_TABLES: tuple[str, ...] = ("product",)

# Handler names — one per subscribed event type. All share the dispatch
# logic in :func:`_handle`.
HANDLER_NAMES = {
    catalog_events.TYPE_BOM_COMPONENT_ADDED: "product_cost_bom_added",
    catalog_events.TYPE_BOM_COMPONENT_REMOVED: "product_cost_bom_removed",
    catalog_events.TYPE_BOM_COMPONENT_QUANTITY_CHANGED: "product_cost_bom_qty_changed",
    inventory_events.TYPE_MATERIAL_RECEIVED: "product_cost_material_received",
    catalog_events.TYPE_SUPPLY_UPDATED: "product_cost_supply_updated",
    catalog_events.TYPE_PRODUCT_COST_CHANGED: "product_cost_product_cost_changed",
    catalog_events.TYPE_PART_COST_CHANGED: "product_cost_part_cost_changed",
    catalog_events.TYPE_PRODUCT_UPDATED: "product_cost_product_updated",
}


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _equal(a: Decimal | None, b: Decimal | None) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a == b


async def _affected_for_bom_event(event: Event, session: AsyncSession) -> set[uuid.UUID]:
    """BOM events: parent + transitive ancestors of the parent."""
    payload = event.payload or {}
    parent_id = uuid.UUID(payload["parent_product_id"])
    ancestors = await bom_service._ancestors_of(parent_id, session=session)
    return {parent_id} | ancestors


async def _affected_for_material_received(event: Event, session: AsyncSession) -> set[uuid.UUID]:
    """Every product whose BOM tree (transitively) contains this material."""
    material_id = event.aggregate_id
    return await bom_service._products_containing_component(
        COMPONENT_KIND_MATERIAL, material_id, session=session
    )


async def _affected_for_supply_updated(event: Event, session: AsyncSession) -> set[uuid.UUID]:
    """Same shape as material — but only when unit_cost actually changed."""
    payload = event.payload or {}
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    if "unit_cost" not in before and "unit_cost" not in after:
        return set()
    supply_id = event.aggregate_id
    return await bom_service._products_containing_component(
        COMPONENT_KIND_SUPPLY, supply_id, session=session
    )


async def _affected_for_part_cost_changed(event: Event, session: AsyncSession) -> set[uuid.UUID]:
    """Every product whose BOM contains this part (epic #267 Phase 3)."""
    part_id = event.aggregate_id
    return await bom_service._products_containing_component(
        COMPONENT_KIND_PART, part_id, session=session
    )


async def _affected_for_product_updated(event: Event, session: AsyncSession) -> set[uuid.UUID]:
    """Only when ``assembly_minutes`` changed — it feeds the cost rollup
    (epic #267 Phase 3). Other product-field edits don't affect cost."""
    payload = event.payload or {}
    after = payload.get("after") or {}
    before = payload.get("before") or {}
    if "assembly_minutes" not in after and "assembly_minutes" not in before:
        return set()
    return {uuid.UUID(payload["product_id"])}


async def _affected_for_product_cost_changed(event: Event, session: AsyncSession) -> set[uuid.UUID]:
    """The changed product's ancestors only (the product itself was just
    updated by the projection step that emitted this event)."""
    payload = event.payload or {}
    product_id = uuid.UUID(payload["product_id"])
    return await bom_service._ancestors_of(product_id, session=session)


_DISPATCH = {
    catalog_events.TYPE_BOM_COMPONENT_ADDED: _affected_for_bom_event,
    catalog_events.TYPE_BOM_COMPONENT_REMOVED: _affected_for_bom_event,
    catalog_events.TYPE_BOM_COMPONENT_QUANTITY_CHANGED: _affected_for_bom_event,
    inventory_events.TYPE_MATERIAL_RECEIVED: _affected_for_material_received,
    catalog_events.TYPE_SUPPLY_UPDATED: _affected_for_supply_updated,
    catalog_events.TYPE_PRODUCT_COST_CHANGED: _affected_for_product_cost_changed,
    catalog_events.TYPE_PART_COST_CHANGED: _affected_for_part_cost_changed,
    catalog_events.TYPE_PRODUCT_UPDATED: _affected_for_product_updated,
}


async def _recompute_one(
    session: AsyncSession, product_id: uuid.UUID, *, actor_user_id: uuid.UUID | None
) -> None:
    """Recompute one product's ``unit_cost_cached``; emit
    ``ProductCostChanged`` iff the value actually changed."""
    try:
        tree = await bom_service.compute_cost_tree(session, product_id=product_id)
    except bom_service.ProductNotFoundError:
        return
    except bom_service.BomServiceError:
        # A stray legacy ``material`` / sub-``product`` BOM row makes
        # ``compute_cost_tree`` hard-fail by design (it surfaces the row
        # loudly on explicit costing). But this is a derived-cache
        # projection running inside someone else's write transaction —
        # the assembly-line migration adds a part line to a product that
        # *still* has its legacy material line (non-destructive by
        # design), and a ``MaterialReceived`` can touch such a product
        # too. Hard-failing here would roll back that legitimate write.
        # Leave the cached cost untouched until the legacy row is
        # resolved; the loud failure still fires on the explicit
        # costing path.
        return

    new_cost = tree.total_cost

    row = (
        await session.execute(select(Product.unit_cost_cached).where(Product.id == product_id))
    ).first()
    if row is None:
        return
    old_cost = _as_decimal(row[0])

    if _equal(old_cost, new_cost):
        return

    await session.execute(
        update(Product).where(Product.id == product_id).values(unit_cost_cached=new_cost)
    )
    await session.flush()

    await event_store.append(
        EventCreate(
            type=catalog_events.TYPE_PRODUCT_COST_CHANGED,
            aggregate_type=catalog_events.PRODUCT_AGGREGATE_TYPE,
            aggregate_id=product_id,
            payload={
                "product_id": str(product_id),
                "old_cost": None if old_cost is None else str(old_cost),
                "new_cost": None if new_cost is None else str(new_cost),
            },
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _handle(event: Event, session: AsyncSession) -> None:
    dispatch = _DISPATCH.get(event.type)
    if dispatch is None:
        return
    affected = await dispatch(event, session)
    if not affected:
        return
    # Topologically tricky: parent costs depend on child costs. We can
    # rely on the projection's own ``ProductCostChanged`` emission to
    # propagate up the tree on subsequent live appends, but for the
    # immediate event we need to walk in *descendant-first* order so a
    # cost change in a leaf product is reflected in its parent's
    # recompute within the same event. The simplest safe ordering is
    # arbitrary plus self-emission: each parent will recompute again on
    # the child's emitted ProductCostChanged. To keep replay
    # deterministic we sort by UUID.
    for product_id in sorted(affected, key=str):
        await _recompute_one(
            session,
            product_id,
            actor_user_id=event.actor_user_id,
        )


# Register one handler per subscribed event type. They all share
# ``_handle`` but the registry needs distinct names.


def _make_handler(event_type: str) -> None:
    name = HANDLER_NAMES[event_type]

    @projection(
        event_type=event_type,
        name=name,
        read_model_tables=READ_MODEL_TABLES,
    )
    async def _handler(event: Event, session: AsyncSession) -> None:
        await _handle(event, session)

    return _handler


for _et in HANDLER_NAMES:
    _make_handler(_et)
