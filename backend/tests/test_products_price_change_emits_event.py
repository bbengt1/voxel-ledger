"""A PATCH that changes ``unit_price`` emits BOTH ProductUpdated and
ProductPriceChanged. Both events share the transaction."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.event import Event
from app.services import products as products_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_price_change_emits_both_events(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    p = await products_service.create(
        session,
        name="Widget",
        description=None,
        unit_price=Decimal("10.00"),
        actor_user_id=None,
    )
    await session.commit()

    await products_service.update(
        session,
        product_id=p.id,
        patch={"unit_price": Decimal("12.50")},
        actor_user_id=None,
    )
    await session.commit()

    types = [
        e.type
        for e in (await session.execute(select(Event).order_by(Event.position))).scalars().all()
    ]
    assert "catalog.ProductUpdated" in types
    assert "catalog.ProductPriceChanged" in types

    pc_payload = (
        (await session.execute(select(Event).where(Event.type == "catalog.ProductPriceChanged")))
        .scalars()
        .one()
        .payload
    )
    assert Decimal(pc_payload["old_price"]) == Decimal("10")
    assert Decimal(pc_payload["new_price"]) == Decimal("12.50")


@pytest.mark.asyncio
async def test_non_price_patch_does_not_emit_price_changed(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    p = await products_service.create(
        session,
        name="Widget",
        description=None,
        unit_price=Decimal("10.00"),
        actor_user_id=None,
    )
    await session.commit()

    await products_service.update(
        session,
        product_id=p.id,
        patch={"name": "Widget Pro"},
        actor_user_id=None,
    )
    await session.commit()

    types = [
        e.type
        for e in (await session.execute(select(Event).order_by(Event.position))).scalars().all()
    ]
    assert "catalog.ProductPriceChanged" not in types
