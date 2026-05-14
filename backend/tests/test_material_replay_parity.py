"""Replay parity for the material_cost projection.

Writes N receipts across a few materials, snapshots the read-side cache
columns, zeros them out, then replays the projection from position 0
and asserts the cache matches the original snapshot bit-for-bit.

This is the load-bearing guarantee Phase 5 depends on: the cost engine
can rebuild ``current_cost_per_gram`` and ``on_hand_grams`` from the
event log alone.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.material import Material
from app.models.projection import ProjectionCursor
from app.projections import registry as projection_registry
from app.projections.material_cost import HANDLER_NAME
from app.projections.replay import replay_handler
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

    # Snapshot the read-model.
    async with factory() as s:
        rows = (await s.execute(select(Material).order_by(Material.id))).scalars().all()
        before = {r.id: (r.on_hand_grams, r.current_cost_per_gram) for r in rows}
    assert all(v[0] > 0 for v in before.values())

    # Zero out the cache columns and drop the projection cursor.
    async with factory() as s:
        await s.execute(
            update(Material).values(on_hand_grams=Decimal("0"), current_cost_per_gram=Decimal("0"))
        )
        await s.execute(
            delete(ProjectionCursor).where(ProjectionCursor.handler_name == HANDLER_NAME)
        )
        await s.commit()

    # Replay the projection from position 0.
    handler = projection_registry.get_handler(HANDLER_NAME)
    await replay_handler(handler, factory, from_position=0)

    # Re-snapshot and compare.
    async with factory() as s:
        rows = (await s.execute(select(Material).order_by(Material.id))).scalars().all()
        after = {r.id: (r.on_hand_grams, r.current_cost_per_gram) for r in rows}

    assert after == before
