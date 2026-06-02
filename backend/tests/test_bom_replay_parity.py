"""Replay parity for the product_cost projection.

The cost rollup must be reproducible from the BOM tables + leaf state
alone. Product BOMs are flat **parts + supplies** since Phase 8b, so this
test:

1. Builds products out of parts + supplies.
2. Recomputes every ``product.unit_cost_cached`` by walking
   ``compute_cost_tree`` (the source of truth the rollup projection uses).
3. Wipes the product costs to NULL and rebuilds.
4. Asserts the rebuilt values match the original snapshot exactly.

This is the load-bearing guarantee the cost engine depends on:
``product.unit_cost_cached`` can always be rebuilt from current BOM
topology plus leaf-level cached costs (part ``unit_cost_cached`` +
supply ``unit_cost``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.product import Product
from app.services import bom as bom_service
from app.services import inventory_locations as locations_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services import parts as parts_service
from app.services import products as products_service
from app.services import supplies as supplies_service
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_bom_replay_parity(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as s:
        await locations_service.create(
            s, name="Receiving", code="RX", kind="workshop", actor_user_id=None
        )
        m = await materials_service.create(
            s,
            name="M",
            brand="X",
            material_type="PLA",
            color=None,
            density_g_per_cm3=None,
            spool_weight_grams=Decimal("1000"),
            actor_user_id=None,
        )
        await receipts_service.record(
            s,
            material_id=m.id,
            grams=Decimal("1000"),
            total_cost=Decimal("15000"),
            actor_user_id=None,
        )
        sup = await supplies_service.create(
            s, name="bag", unit="ea", unit_cost=Decimal("0.25"), vendor=None, actor_user_id=None
        )
        part_a = await parts_service.create(
            s,
            name="part-a",
            print_minutes=0,
            setup_minutes=0,
            parts_per_run=1,
            print_grams_by_material={m.id: Decimal("50")},
            actor_user_id=None,
        )
        part_b = await parts_service.create(
            s,
            name="part-b",
            print_minutes=0,
            setup_minutes=0,
            parts_per_run=1,
            print_grams_by_material={m.id: Decimal("25")},
            actor_user_id=None,
        )
        p_one = await products_service.create(
            s, name="one", description=None, unit_price=Decimal("10"), actor_user_id=None
        )
        p_two = await products_service.create(
            s, name="two", description=None, unit_price=Decimal("20"), actor_user_id=None
        )
        await s.commit()

    # Flat product BOMs: one = 1 part_a + 4 bag; two = 2 part_b + 1 bag.
    async with factory() as s:
        for parent_id, kind, comp_id, qty in [
            (p_one.id, "part", part_a.id, "1"),
            (p_one.id, "supply", sup.id, "4"),
            (p_two.id, "part", part_b.id, "2"),
            (p_two.id, "supply", sup.id, "1"),
        ]:
            await bom_service.add_component(
                s,
                parent_product_id=parent_id,
                component_kind=kind,
                component_id=comp_id,
                quantity=Decimal(qty),
                actor_user_id=None,
            )
        await s.commit()

    async def _rebuild() -> dict:
        async with factory() as s:
            product_ids = list((await s.execute(select(Product.id))).scalars().all())
        async with factory() as s:
            for pid in product_ids:
                tree = await bom_service.compute_cost_tree(s, product_id=pid)
                await s.execute(
                    update(Product)
                    .where(Product.id == pid)
                    .values(unit_cost_cached=tree.total_cost)
                )
            await s.commit()
        async with factory() as s:
            rows = (await s.execute(select(Product).order_by(Product.id))).scalars().all()
            return {r.id: r.unit_cost_cached for r in rows}

    # First build → snapshot, wipe product costs, rebuild → must match.
    before = await _rebuild()
    assert all(v is not None for v in before.values())

    async with factory() as s:
        await s.execute(update(Product).values(unit_cost_cached=None))
        await s.commit()

    after = await _rebuild()
    assert after == before
