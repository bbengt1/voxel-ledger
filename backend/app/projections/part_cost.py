"""Projection: cache ``part.unit_cost_cached`` from the part's recipe (Phase 2).

A part's unit cost is computed by the cost engine from its print recipe
(materials x cost/gram + labor + machine + overhead + failure buffer,
divided by ``parts_per_run``). This projection keeps the cached value fresh.

Subscribes to:
* ``catalog.PartCreated`` / ``catalog.PartUpdated`` — recompute that part.
* ``inventory.MaterialReceived`` — recompute every part whose recipe uses
  that material (its cost/gram moved).

On a real change it writes ``unit_cost_cached`` and emits
``catalog.PartCostChanged`` (Phase 3's product rollup will subscribe).

Rate changes (labor/machine/overhead) also affect part cost but are not
event-driven here; use ``recompute_all`` (exposed via the
``POST /parts/recompute-costs`` admin action) after changing rates.

If the cost engine can't price the part (e.g. no rate config), the cached
value is left as NULL ("cost pending") — a mutation must never fail just
because pricing isn't configured yet.
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
from app.models.part import Part
from app.projections.registry import projection
from app.schemas.events import EventCreate
from app.services import event_store

log = logging.getLogger(__name__)

READ_MODEL_TABLES: tuple[str, ...] = ("part",)

HANDLER_NAMES = {
    catalog_events.TYPE_PART_CREATED: "part_cost_part_created",
    catalog_events.TYPE_PART_UPDATED: "part_cost_part_updated",
    inventory_events.TYPE_MATERIAL_RECEIVED: "part_cost_material_received",
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


async def _compute_cost(session: AsyncSession, part: Part) -> Decimal | None:
    """Cost-engine cost-per-piece for a part, or None when unpriceable."""
    # Imported lazily: this projection module is eager-imported at startup
    # (via the event store), and the cost-engine service pulls in jobs /
    # event_store, which would form an import cycle at module load.
    from app.services.cost_engine.service import CostEngineService, MissingRateConfigError

    try:
        result = await CostEngineService.calculate_for_part(part, session=session)
    except MissingRateConfigError:
        # Pricing not configured yet — leave the cache NULL.
        return None
    return result.cost_per_piece


async def recompute_part(
    session: AsyncSession, part_id: uuid.UUID, *, actor_user_id: uuid.UUID | None
) -> None:
    """Recompute one part's ``unit_cost_cached``; emit ``PartCostChanged``
    iff the value actually changed."""
    part = (await session.execute(select(Part).where(Part.id == part_id))).scalar_one_or_none()
    if part is None:
        return
    old_cost = _as_decimal(part.unit_cost_cached)
    new_cost = await _compute_cost(session, part)
    if _equal(old_cost, new_cost):
        return
    await session.execute(update(Part).where(Part.id == part_id).values(unit_cost_cached=new_cost))
    await session.flush()
    await event_store.append(
        EventCreate(
            type=catalog_events.TYPE_PART_COST_CHANGED,
            aggregate_type=catalog_events.PART_AGGREGATE_TYPE,
            aggregate_id=part_id,
            payload={
                "part_id": str(part_id),
                "old_cost": None if old_cost is None else str(old_cost),
                "new_cost": None if new_cost is None else str(new_cost),
            },
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _parts_using_material(session: AsyncSession, material_id: uuid.UUID) -> list[uuid.UUID]:
    """Part ids whose ``print_grams_by_material`` references the material.

    Filtered in Python for SQLite/Postgres portability — the parts catalog
    is small enough that a full scan is fine.
    """
    key = str(material_id)
    rows = (await session.execute(select(Part.id, Part.print_grams_by_material))).all()
    return [pid for pid, grams in rows if isinstance(grams, dict) and key in grams]


async def recompute_all(session: AsyncSession, *, actor_user_id: uuid.UUID | None) -> int:
    """Recompute every part's cost (e.g. after a rate change). Returns count."""
    ids = [row[0] for row in (await session.execute(select(Part.id))).all()]
    for part_id in ids:
        await recompute_part(session, part_id, actor_user_id=actor_user_id)
    return len(ids)


async def _handle(event: Event, session: AsyncSession) -> None:
    if event.type in (
        catalog_events.TYPE_PART_CREATED,
        catalog_events.TYPE_PART_UPDATED,
    ):
        await recompute_part(session, event.aggregate_id, actor_user_id=event.actor_user_id)
    elif event.type == inventory_events.TYPE_MATERIAL_RECEIVED:
        affected = await _parts_using_material(session, event.aggregate_id)
        for part_id in sorted(affected, key=str):
            await recompute_part(session, part_id, actor_user_id=event.actor_user_id)


def _make_handler(event_type: str) -> None:
    name = HANDLER_NAMES[event_type]

    @projection(event_type=event_type, name=name, read_model_tables=READ_MODEL_TABLES)
    async def _handler(event: Event, session: AsyncSession) -> None:
        await _handle(event, session)

    return _handler


for _et in HANDLER_NAMES:
    _make_handler(_et)
