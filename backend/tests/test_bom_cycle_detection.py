"""Product BOM component-kind contract + legacy cycle-walk coverage.

Epic #267 Phase 3: product BOMs accept only ``part`` / ``supply`` — the
old product-in-product (sub-assembly) path is rejected at ``add_component``.
The cycle-walk helper still exists for legacy-shaped data, exercised here
via direct row insertion.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.product_bom_item import ProductBomItem
from app.services import bom as bom_service
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def _setup(engine) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.mark.asyncio
async def test_product_and_material_components_rejected(engine) -> None:
    """New product BOMs accept only part/supply (epic #267 decision #3)."""
    factory = await _setup(engine)
    async with factory() as s:
        a = await products_service.create(
            s, name="A", description=None, unit_price=Decimal("1"), actor_user_id=None
        )
        await s.commit()

    for kind in ("product", "material"):
        async with factory() as s:
            with pytest.raises(bom_service.InvalidComponentKindError):
                await bom_service.add_component(
                    s,
                    parent_product_id=a.id,
                    component_kind=kind,
                    component_id=a.id,
                    quantity=Decimal("1"),
                    actor_user_id=None,
                )


@pytest.mark.asyncio
async def test_legacy_cycle_walk_finds_descendant(engine) -> None:
    """The cycle-walk helper still traverses legacy product→product rows."""
    factory = await _setup(engine)
    async with factory() as s:
        a = await products_service.create(
            s, name="A", description=None, unit_price=Decimal("1"), actor_user_id=None
        )
        b = await products_service.create(
            s, name="B", description=None, unit_price=Decimal("1"), actor_user_id=None
        )
        c = await products_service.create(
            s, name="C", description=None, unit_price=Decimal("1"), actor_user_id=None
        )
        # a → b → c (legacy-shaped sub-assembly rows, inserted directly).
        s.add(
            ProductBomItem(
                parent_product_id=a.id,
                component_kind="product",
                component_id=b.id,
                quantity=Decimal("1"),
            )
        )
        s.add(
            ProductBomItem(
                parent_product_id=b.id,
                component_kind="product",
                component_id=c.id,
                quantity=Decimal("1"),
            )
        )
        await s.commit()

    async with factory() as s:
        found, path = await bom_service._walks_back_to(c.id, a.id, session=s)
        assert found is True
        assert c.id in path
