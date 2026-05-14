"""Default-receiving-location resolution chain.

Setting → lowest-code workshop location → 400.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.services import inventory_locations as locations_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_fallback_to_lowest_code_workshop_when_setting_unset(
    session: AsyncSession, engine
) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Two workshop locations; the lower code wins as the fallback.
    high = await locations_service.create(
        session, name="High", code="ZWS", kind="workshop", actor_user_id=None
    )
    low = await locations_service.create(
        session, name="Low", code="AAA", kind="workshop", actor_user_id=None
    )
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    await receipts_service.record(
        session,
        material_id=mat.id,
        grams=Decimal("100"),
        total_cost=Decimal("5"),
        actor_user_id=None,
    )
    await session.commit()

    from app.models.inventory_transaction import InventoryTransaction
    from sqlalchemy import select

    rows = (await session.execute(select(InventoryTransaction))).scalars().all()
    assert len(rows) == 1
    assert rows[0].location_id == low.id
    assert rows[0].location_id != high.id


@pytest.mark.asyncio
async def test_setting_overrides_fallback(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    workshop = await locations_service.create(
        session, name="WS", code="A", kind="workshop", actor_user_id=None
    )
    staging = await locations_service.create(
        session, name="ST", code="Z", kind="staging", actor_user_id=None
    )
    # Explicit setting: route receipts into the staging location even
    # though there's an active workshop on the table.
    await SettingsService.set(
        "inventory.default_receiving_location_id",
        staging.id,
        session=session,
        actor_user_id=None,
    )
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    await receipts_service.record(
        session,
        material_id=mat.id,
        grams=Decimal("100"),
        total_cost=Decimal("5"),
        actor_user_id=None,
    )
    await session.commit()

    from app.models.inventory_transaction import InventoryTransaction
    from sqlalchemy import select

    rows = (await session.execute(select(InventoryTransaction))).scalars().all()
    assert rows[0].location_id == staging.id
    assert rows[0].location_id != workshop.id


@pytest.mark.asyncio
async def test_raises_when_no_workshop_and_no_setting(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # No locations at all → fallback chain bottoms out.
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    with pytest.raises(receipts_service.InventoryConfigError):
        await receipts_service.record(
            session,
            material_id=mat.id,
            grams=Decimal("100"),
            total_cost=Decimal("5"),
            actor_user_id=None,
        )
