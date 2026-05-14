"""Cycle detection across product BOM relationships."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.services import bom as bom_service
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def _setup(engine) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.mark.asyncio
async def test_self_reference_rejected(engine) -> None:
    factory = await _setup(engine)
    async with factory() as s:
        a = await products_service.create(
            s,
            name="A",
            description=None,
            unit_price=Decimal("1"),
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        with pytest.raises(bom_service.BomCycleError):
            await bom_service.add_component(
                s,
                parent_product_id=a.id,
                component_kind="product",
                component_id=a.id,
                quantity=Decimal("1"),
                actor_user_id=None,
            )


@pytest.mark.asyncio
async def test_three_deep_cycle_rejected(engine) -> None:
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
        await s.commit()

    async with factory() as s:
        # B in A, C in B — legal.
        await bom_service.add_component(
            s,
            parent_product_id=a.id,
            component_kind="product",
            component_id=b.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=b.id,
            component_kind="product",
            component_id=c.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
        await s.commit()

    # C in A — legal (diamond, not a cycle).
    async with factory() as s:
        await bom_service.add_component(
            s,
            parent_product_id=a.id,
            component_kind="product",
            component_id=c.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
        await s.commit()

    # A in C — would close the cycle. Reject.
    async with factory() as s:
        with pytest.raises(bom_service.BomCycleError) as exc_info:
            await bom_service.add_component(
                s,
                parent_product_id=c.id,
                component_kind="product",
                component_id=a.id,
                quantity=Decimal("1"),
                actor_user_id=None,
            )
        assert "cycle" in str(exc_info.value).lower()
