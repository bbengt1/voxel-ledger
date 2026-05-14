"""Material-cost projection: weighted-average cost-per-gram correctness.

The headline test specified in #37 (now updated for Phase 3.3 #52):
on-hand grams have moved to ``inventory_on_hand`` and are summed across
locations, but the cost math still tracks the same running weighted
average.

  Receipt 1: 1000g @ $20/g  -> cost = $20.000000/g, on_hand = 1000g
  Receipt 2:  500g @ $10/g  -> cost = $16.666667/g, on_hand = 1500g
  Receipt 3:  200g @ $25/g  -> cost = $17.647059/g, on_hand = 1700g
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.services import inventory_alerts as alerts_service
from app.services import inventory_locations as locations_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_receiving_location(session) -> None:
    """Phase 3.2: receipts need a fallback workshop location."""
    await locations_service.create(
        session,
        name="Receiving",
        code="RX",
        kind="workshop",
        actor_user_id=None,
    )


async def _total_on_hand(session, material_id) -> Decimal:
    return await alerts_service.total_on_hand_for_entity(
        session=session, entity_kind="material", entity_id=material_id
    )


@pytest.mark.asyncio
async def test_weighted_average_three_receipts(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_receiving_location(session)

    m = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )

    # Receipt 1
    await receipts_service.record(
        session,
        material_id=m.id,
        grams=Decimal("1000"),
        total_cost=Decimal("20000.00"),  # $20/g
        actor_user_id=None,
    )
    fresh = await materials_service.get(session, m.id)
    assert await _total_on_hand(session, m.id) == Decimal("1000.000000")
    assert fresh.current_cost_per_gram == Decimal("20.000000")

    # Receipt 2 — weighted average: (1000*20 + 500*10) / 1500 = 16.666667
    await receipts_service.record(
        session,
        material_id=m.id,
        grams=Decimal("500"),
        total_cost=Decimal("5000.00"),  # $10/g
        actor_user_id=None,
    )
    fresh = await materials_service.get(session, m.id)
    assert await _total_on_hand(session, m.id) == Decimal("1500.000000")
    assert fresh.current_cost_per_gram == Decimal("16.666667")

    # Receipt 3 — weighted average over the running average (lossy, as
    # designed): (1500 * 16.666667 + 200 * 25) / 1700 = 17.647059
    await receipts_service.record(
        session,
        material_id=m.id,
        grams=Decimal("200"),
        total_cost=Decimal("5000.00"),  # $25/g
        actor_user_id=None,
    )
    fresh = await materials_service.get(session, m.id)
    assert await _total_on_hand(session, m.id) == Decimal("1700.000000")
    assert fresh.current_cost_per_gram == Decimal("17.647059")


@pytest.mark.asyncio
async def test_first_receipt_seeds_cost(session: AsyncSession, engine) -> None:
    """Edge case: old_on_hand == 0 -> new_cost = receipt_unit_cost."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_receiving_location(session)

    m = await materials_service.create(
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
        material_id=m.id,
        grams=Decimal("123.456"),
        total_cost=Decimal("100.00"),
        actor_user_id=None,
    )
    fresh = await materials_service.get(session, m.id)
    # 100 / 123.456 = 0.810005...
    assert fresh.current_cost_per_gram == Decimal("0.810005")
    assert await _total_on_hand(session, m.id) == Decimal("123.456000")
