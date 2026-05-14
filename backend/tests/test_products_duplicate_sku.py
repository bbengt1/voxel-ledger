"""Duplicate manual SKUs are rejected with a typed error → 400 at the router."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_duplicate_manual_sku_raises(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await products_service.create(
        session,
        name="Thing 1",
        description=None,
        unit_price=Decimal("1.00"),
        sku="DUP-001",
        actor_user_id=None,
    )
    await session.commit()
    with pytest.raises(products_service.DuplicateSkuError):
        await products_service.create(
            session,
            name="Thing 2",
            description=None,
            unit_price=Decimal("2.00"),
            sku="DUP-001",
            actor_user_id=None,
        )
