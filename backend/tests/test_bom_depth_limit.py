"""Depth limit on cycle walks."""

from __future__ import annotations

import itertools
from decimal import Decimal

import pytest
from app.models import Base
from app.services import bom as bom_service
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_depth_limit_fires(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Build a 6-deep chain and assert depth-limit=3 fires while
    # depth-limit=10 does not. (Building 50+ products in SQLite for a
    # unit test would be wasteful — exercising the limit at a small value
    # is what matters; the integer is a parameter.)
    async with factory() as s:
        chain = []
        for i in range(6):
            p = await products_service.create(
                s,
                name=f"P{i}",
                description=None,
                unit_price=Decimal("1"),
                actor_user_id=None,
            )
            chain.append(p)
        await s.commit()

    async with factory() as s:
        for parent, child in itertools.pairwise(chain):
            await bom_service.add_component(
                s,
                parent_product_id=parent.id,
                component_kind="product",
                component_id=child.id,
                quantity=Decimal("1"),
                actor_user_id=None,
            )
        await s.commit()

    # Walking from chain[0] descends 5 levels. Limit=3 must trip.
    async with factory() as s:
        with pytest.raises(bom_service.BomDepthLimitError):
            await bom_service._walks_back_to(chain[0].id, chain[0].id, session=s, max_depth=3)

    # Limit=10 must not.
    async with factory() as s:
        found, _ = await bom_service._walks_back_to(
            chain[0].id, chain[0].id, session=s, max_depth=10
        )
        assert found is False
