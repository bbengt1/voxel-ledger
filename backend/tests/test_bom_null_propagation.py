"""NULL propagation: a missing leaf component renders the whole rollup
NULL. Replacing the missing leaf with a real one restores the rollup.

A "missing" component is a row in ``product_bom_item`` pointing at a
component_id that no longer exists in its target table (polymorphic
ref with no FK). The cost-tree walk treats that as unknown and
propagates NULL upward."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models import Base
from app.models.product import Product
from app.models.product_bom_item import ProductBomItem
from app.services import bom as bom_service
from app.services import products as products_service
from app.services import supplies as supplies_service
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_null_propagates_and_restores(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as s:
        p_inner = await products_service.create(
            s, name="P_inner", description=None, unit_price=Decimal("1"), actor_user_id=None
        )
        p_outer = await products_service.create(
            s, name="P_outer", description=None, unit_price=Decimal("1"), actor_user_id=None
        )
        supply = await supplies_service.create(
            s,
            name="bag",
            unit="ea",
            unit_cost=Decimal("3"),
            vendor=None,
            on_hand=Decimal("0"),
            actor_user_id=None,
        )
        await s.commit()

    # Build: p_inner = 2 bag (cost 6); p_outer = 1 p_inner.
    async with factory() as s:
        inner_bom_item = await bom_service.add_component(
            s,
            parent_product_id=p_inner.id,
            component_kind="supply",
            component_id=supply.id,
            quantity=Decimal("2"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p_outer.id,
            component_kind="product",
            component_id=p_inner.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
        await s.commit()
        inner_bom_item_id = inner_bom_item.id

    async with factory() as s:
        outer = (await s.execute(select(Product).where(Product.id == p_outer.id))).scalar_one()
        assert outer.unit_cost_cached == Decimal("6.000000")

    # Break the leaf: point the supply BOM row at a non-existent supply
    # (polymorphic ref, no FK).
    async with factory() as s:
        await s.execute(
            update(ProductBomItem)
            .where(ProductBomItem.id == inner_bom_item_id)
            .values(component_id=uuid.uuid4())
        )
        await s.commit()

    # Trigger a recompute by walking the tree directly (no event was
    # emitted by the raw UPDATE, but compute_cost_tree is the source of
    # truth used by the rollup projection).
    async with factory() as s:
        tree = await bom_service.compute_cost_tree(s, product_id=p_outer.id)
    assert tree.total_cost is None

    # Restore: re-point the BOM item back at the real supply.
    async with factory() as s:
        await s.execute(
            update(ProductBomItem)
            .where(ProductBomItem.id == inner_bom_item_id)
            .values(component_id=supply.id)
        )
        await s.commit()

    async with factory() as s:
        tree = await bom_service.compute_cost_tree(s, product_id=p_outer.id)
    assert tree.total_cost == Decimal("6.000000")
