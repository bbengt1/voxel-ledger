"""Multi-level cost rollup with material-receipt propagation."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.events.types import catalog as catalog_events
from app.models import Base
from app.models.event import Event
from app.models.product import Product
from app.services import bom as bom_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services import products as products_service
from app.services import supplies as supplies_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_multi_level_cost_rollup(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed: material M @ $20/g, supply S @ $5/ea.
    async with factory() as s:
        m = await materials_service.create(
            s,
            name="M",
            brand="X",
            material_type="PLA",
            color=None,
            density_g_per_cm3=None,
            actor_user_id=None,
        )
        await receipts_service.record(
            s,
            material_id=m.id,
            grams=Decimal("1000"),
            total_cost=Decimal("20000"),
            actor_user_id=None,
        )
        supply = await supplies_service.create(
            s,
            name="S",
            unit="ea",
            unit_cost=Decimal("5"),
            vendor=None,
            on_hand=Decimal("0"),
            actor_user_id=None,
        )
        p1 = await products_service.create(
            s,
            name="P1",
            description=None,
            unit_price=Decimal("100"),
            actor_user_id=None,
        )
        p2 = await products_service.create(
            s,
            name="P2",
            description=None,
            unit_price=Decimal("200"),
            actor_user_id=None,
        )
        await s.commit()

    # Build P1 = 100g M + 2 S; P2 = 1 P1 + 50g M.
    async with factory() as s:
        await bom_service.add_component(
            s,
            parent_product_id=p1.id,
            component_kind="material",
            component_id=m.id,
            quantity=Decimal("100"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p1.id,
            component_kind="supply",
            component_id=supply.id,
            quantity=Decimal("2"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p2.id,
            component_kind="product",
            component_id=p1.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p2.id,
            component_kind="material",
            component_id=m.id,
            quantity=Decimal("50"),
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        p1_row = (await s.execute(select(Product).where(Product.id == p1.id))).scalar_one()
        p2_row = (await s.execute(select(Product).where(Product.id == p2.id))).scalar_one()
        assert p1_row.unit_cost_cached == Decimal("2010.000000")
        assert p2_row.unit_cost_cached == Decimal("3010.000000")

    # Record a second receipt that brings cost-per-gram to $25.
    # Weighted avg: (1000*20 + R*25) / (1000+R) = 25 => R must be very
    # large; instead, give a clean weighted shift via a receipt with
    # known math. Use a receipt of 1000g at total_cost = 30000 — then
    # avg = (20000 + 30000) / 2000 = 25.
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
        p1_row = (await s.execute(select(Product).where(Product.id == p1.id))).scalar_one()
        p2_row = (await s.execute(select(Product).where(Product.id == p2.id))).scalar_one()
        # 100 * 25 + 2 * 5 = 2510.
        assert p1_row.unit_cost_cached == Decimal("2510.000000")
        # 2510 + 50 * 25 = 3760.
        assert p2_row.unit_cost_cached == Decimal("3760.000000")

    # ProductCostChanged events were emitted for both p1 and p2 at least
    # twice (once at BOM build, once at receipt).
    async with factory() as s:
        rows = (
            await s.execute(
                select(Event.aggregate_id).where(
                    Event.type == catalog_events.TYPE_PRODUCT_COST_CHANGED
                )
            )
        ).all()
        agg_ids = {r[0] for r in rows}
        assert p1.id in agg_ids
        assert p2.id in agg_ids
