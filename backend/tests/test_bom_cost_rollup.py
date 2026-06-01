"""Product cost rollup from parts + supplies, with PartCostChanged
propagation (assembly-line epic #267 Phase 3).

A product's cost = Σ(part.unit_cost_cached x qty) + Σ(supply per-piece x
qty) + assembly labor (a plain sum — parts already carry their overhead).
When a material's cost moves, the part recomputes (Phase 2a) and the
resulting ``PartCostChanged`` propagates to every product using that part.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.part import Part
from app.models.product import Product
from app.models.supply import Supply
from app.services import bom as bom_service
from app.services import inventory_locations as locations_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services import parts as parts_service
from app.services import products as products_service
from app.services import supplies as supplies_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_product_cost_rolls_up_parts_and_supplies(engine) -> None:
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
            total_cost=Decimal("20000"),
            actor_user_id=None,
        )  # $20/g
        supply = await supplies_service.create(
            s, name="S", unit="ea", unit_cost=Decimal("5"), vendor=None, actor_user_id=None
        )
        # A part that prints 100 g of M per run (1 part/run).
        part = await parts_service.create(
            s,
            name="Widget body",
            print_minutes=0,
            setup_minutes=0,
            parts_per_run=1,
            print_grams_by_material={m.id: Decimal("100")},
            actor_user_id=None,
        )
        product = await products_service.create(
            s, name="Widget", description=None, unit_price=Decimal("100"), actor_user_id=None
        )
        await s.commit()
        product_id, part_id, supply_id = product.id, part.id, supply.id

    # Product = 2 x part + 3 x supply (no assembly labor).
    async with factory() as s:
        await bom_service.add_component(
            s,
            parent_product_id=product_id,
            component_kind="part",
            component_id=part_id,
            quantity=Decimal("2"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=product_id,
            component_kind="supply",
            component_id=supply_id,
            quantity=Decimal("3"),
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        part_cost = (
            await s.execute(select(Part.unit_cost_cached).where(Part.id == part_id))
        ).scalar_one()
        supply_cost = (
            await s.execute(select(Supply.unit_cost).where(Supply.id == supply_id))
        ).scalar_one()
        product_cost = (
            await s.execute(select(Product.unit_cost_cached).where(Product.id == product_id))
        ).scalar_one()
        # Plain sum: 2 parts + 3 supplies, no extra overhead (decision #2).
        assert part_cost is not None
        assert product_cost == (Decimal("2") * part_cost + Decimal("3") * supply_cost)

    # Material cost moves → part recomputes → PartCostChanged → product
    # recomputes. avg = (20000 + 30000) / 2000 = $25/g.
    async with factory() as s:
        await receipts_service.record(
            s,
            material_id=m.id,
            grams=Decimal("1000"),
            total_cost=Decimal("30000"),
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        new_part_cost = (
            await s.execute(select(Part.unit_cost_cached).where(Part.id == part_id))
        ).scalar_one()
        new_product_cost = (
            await s.execute(select(Product.unit_cost_cached).where(Product.id == product_id))
        ).scalar_one()
        assert new_part_cost > part_cost  # material got more expensive
        assert new_product_cost == (Decimal("2") * new_part_cost + Decimal("3") * supply_cost)
