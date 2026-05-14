"""Headline SKU-allocation behavior.

Three sequential creates without a SKU should get
``PROD-YYYY-0001``, ``0002``, ``0003``. A fourth create with a manual
SKU should be accepted verbatim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models import Base
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_auto_sku_increments_and_manual_override(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    year = datetime.now(UTC).year
    skus = []
    for _ in range(3):
        p = await products_service.create(
            session,
            name="Widget",
            description=None,
            unit_price=Decimal("9.99"),
            actor_user_id=None,
        )
        skus.append(p.sku)
    assert skus == [
        f"PROD-{year}-0001",
        f"PROD-{year}-0002",
        f"PROD-{year}-0003",
    ]

    manual = await products_service.create(
        session,
        name="Specialty Widget",
        description=None,
        unit_price=Decimal("19.99"),
        sku="CUSTOM-001",
        actor_user_id=None,
    )
    assert manual.sku == "CUSTOM-001"
    await session.commit()
