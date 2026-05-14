"""Lookup-by-code: SKU first, then UPC, else 404."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_lookup_by_sku_and_upc(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    p = await products_service.create(
        session,
        name="Scanner Bait",
        description=None,
        unit_price=Decimal("4.20"),
        sku="LK-001",
        upc="012345678905",
        actor_user_id=None,
    )
    await session.commit()

    by_sku = await products_service.lookup_by_code(session, "LK-001")
    assert by_sku.id == p.id

    by_upc = await products_service.lookup_by_code(session, "012345678905")
    assert by_upc.id == p.id

    with pytest.raises(products_service.ProductNotFoundError):
        await products_service.lookup_by_code(session, "NOPE-999")
