"""Replay parity for the material_cost projection (Phase 3.3 refactor).

Writes N receipts across a few materials, snapshots the read-side cache
column, zeros it out, then replays the projection from position 0 and
asserts the cache matches the original snapshot bit-for-bit.

Phase 3.3: on-hand grams have moved to ``inventory_on_hand``. The
material_cost projection now depends on the on-hand projection's read
model. Replay must populate ``inventory_on_hand`` first (or the
material_cost replay would see zero balances and recompute as if every
receipt were the first). We replay both handlers from position 0.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.inventory_on_hand import InventoryOnHand
from app.models.material import Material
from app.models.projection import ProjectionCursor
from app.projections import registry as projection_registry
from app.projections.inventory_on_hand import HANDLER_NAME as ON_HAND_HANDLER_NAME
from app.projections.material_cost import HANDLER_NAME
from app.services import inventory_locations as locations_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_material_cost_replay_parity(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed two materials and a varied receipt pattern.
    material_ids = []
    async with factory() as s:
        # Phase 3.2: receipts need a fallback receiving location.
        await locations_service.create(
            s, name="Receiving", code="RX", kind="workshop", actor_user_id=None
        )
        for name in ("PLA-A", "PETG-B"):
            m = await materials_service.create(
                s,
                name=name,
                brand="X",
                material_type=name.split("-")[0],
                color=None,
                density_g_per_cm3=None,
                actor_user_id=None,
            )
            material_ids.append(m.id)
        await s.commit()

    receipts_by_material = {
        material_ids[0]: [
            (Decimal("1000"), Decimal("20000.00")),
            (Decimal("500"), Decimal("5000.00")),
            (Decimal("200"), Decimal("5000.00")),
        ],
        material_ids[1]: [
            (Decimal("750"), Decimal("18000.00")),
            (Decimal("250"), Decimal("4000.00")),
        ],
    }
    async with factory() as s:
        for mid, receipts in receipts_by_material.items():
            for grams, total in receipts:
                await receipts_service.record(
                    s,
                    material_id=mid,
                    grams=grams,
                    total_cost=total,
                    actor_user_id=None,
                )
        await s.commit()

    # Snapshot the read-model: material cost cache + the on-hand totals.
    async with factory() as s:
        mat_rows = (await s.execute(select(Material).order_by(Material.id))).scalars().all()
        before_cost = {r.id: r.current_cost_per_gram for r in mat_rows}
        oh_rows = (
            (
                await s.execute(
                    select(InventoryOnHand).order_by(
                        InventoryOnHand.entity_kind,
                        InventoryOnHand.entity_id,
                        InventoryOnHand.location_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        before_on_hand = {(r.entity_kind, r.entity_id, r.location_id): r.on_hand for r in oh_rows}
    assert all(v > 0 for v in before_on_hand.values())

    # Zero out the cache + read-model tables, drop both projections' cursors.
    async with factory() as s:
        await s.execute(update(Material).values(current_cost_per_gram=Decimal("0")))
        await s.execute(delete(InventoryOnHand))
        await s.execute(
            delete(ProjectionCursor).where(
                ProjectionCursor.handler_name.in_([HANDLER_NAME, ON_HAND_HANDLER_NAME])
            )
        )
        await s.commit()

    # Replay events in position order, dispatching every event through
    # both subscribed handlers in the same transaction (mirroring live
    # append). Each event lands in its own write session so the
    # post-event state is durable before the next event runs.
    on_hand_handler = projection_registry.get_handler(ON_HAND_HANDLER_NAME)
    cost_handler = projection_registry.get_handler(HANDLER_NAME)
    from app.services import event_store

    async with factory() as read_s:
        async for ev in event_store.read(read_s, from_position=0):
            async with factory() as write_s:
                for handler in (on_hand_handler, cost_handler):
                    if handler.event_type == ev.type:
                        await handler.fn(ev, write_s)
                await write_s.commit()

    # Re-snapshot and compare.
    async with factory() as s:
        mat_rows = (await s.execute(select(Material).order_by(Material.id))).scalars().all()
        after_cost = {r.id: r.current_cost_per_gram for r in mat_rows}
        oh_rows = (
            (
                await s.execute(
                    select(InventoryOnHand).order_by(
                        InventoryOnHand.entity_kind,
                        InventoryOnHand.entity_id,
                        InventoryOnHand.location_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        after_on_hand = {(r.entity_kind, r.entity_id, r.location_id): r.on_hand for r in oh_rows}

    assert after_on_hand == before_on_hand
    assert after_cost == before_cost
