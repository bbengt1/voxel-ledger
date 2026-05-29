"""Spool-centric receipt entry (#11).

Exercises the new ``record_from_spools`` service path: math, validation,
and the SpoolWeightNotConfiguredError guard.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from sqlalchemy.ext.asyncio import AsyncSession


async def _setup_workshop(session: AsyncSession) -> InventoryLocation:
    loc = InventoryLocation(
        code="WS-1",
        name="Workshop",
        kind=InventoryLocationKind.WORKSHOP,
        is_archived=False,
    )
    session.add(loc)
    await session.flush()
    return loc


@pytest.mark.asyncio
async def test_record_from_spools_whole_spool(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _setup_workshop(session)

    m = await materials_service.create(
        session,
        name="PLA",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    r = await receipts_service.record_from_spools(
        session,
        material_id=m.id,
        spools=5,
        extra_grams=Decimal("0"),
        price_per_spool=Decimal("24.99"),
        actor_user_id=None,
    )
    await session.commit()
    assert r.grams == Decimal("5000")
    assert r.total_cost == Decimal("124.95")


@pytest.mark.asyncio
async def test_record_from_spools_partial_only(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _setup_workshop(session)

    m = await materials_service.create(
        session,
        name="PETG",
        brand=None,
        material_type="PETG",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    r = await receipts_service.record_from_spools(
        session,
        material_id=m.id,
        spools=0,
        extra_grams=Decimal("300"),
        price_per_spool=Decimal("20"),
        actor_user_id=None,
    )
    await session.commit()
    assert r.grams == Decimal("300")
    # 20 * (0 + 300/1000) == 6.0
    assert r.total_cost == Decimal("6.0")


@pytest.mark.asyncio
async def test_record_from_spools_mixed(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _setup_workshop(session)

    m = await materials_service.create(
        session,
        name="ASA",
        brand=None,
        material_type="ASA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("750"),
        actor_user_id=None,
    )
    r = await receipts_service.record_from_spools(
        session,
        material_id=m.id,
        spools=2,
        extra_grams=Decimal("250"),
        price_per_spool=Decimal("30"),
        actor_user_id=None,
    )
    await session.commit()
    # grams = 2 * 750 + 250 = 1750
    assert r.grams == Decimal("1750")
    # cost = 30 * (2 + 250/750) = 30 * 2.333... = 70.0 after quantize.
    assert r.total_cost == Decimal("70.000000")


@pytest.mark.asyncio
async def test_record_rejects_extra_at_or_above_spool_weight(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _setup_workshop(session)

    m = await materials_service.create(
        session,
        name="PLA",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    with pytest.raises(receipts_service.InvalidExtraGramsError):
        await receipts_service.record_from_spools(
            session,
            material_id=m.id,
            spools=0,
            extra_grams=Decimal("1000"),
            price_per_spool=Decimal("20"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_record_rejects_zero_quantity(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _setup_workshop(session)

    m = await materials_service.create(
        session,
        name="PLA",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    with pytest.raises(receipts_service.InvalidGramsError):
        await receipts_service.record_from_spools(
            session,
            material_id=m.id,
            spools=0,
            extra_grams=Decimal("0"),
            price_per_spool=Decimal("20"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_record_rejects_when_spool_weight_zero(session: AsyncSession, engine) -> None:
    """Legacy rows (spool_weight = 0) must reject receipts until backfilled."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _setup_workshop(session)

    # Bypass the service validator (which blocks 0) by writing the row directly.
    from app.models.material import Material

    legacy = Material(
        name="Legacy PLA",
        material_type="PLA",
        spool_weight_grams=Decimal("0"),
    )
    session.add(legacy)
    await session.flush()

    with pytest.raises(receipts_service.SpoolWeightNotConfiguredError):
        await receipts_service.record_from_spools(
            session,
            material_id=legacy.id,
            spools=1,
            extra_grams=Decimal("0"),
            price_per_spool=Decimal("20"),
            actor_user_id=None,
        )
