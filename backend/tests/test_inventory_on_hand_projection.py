"""Phase 3.3 (#52) inventory_on_hand projection correctness."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.inventory_on_hand import InventoryOnHand
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as transactions_service
from app.services import materials as materials_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed(session):
    loc1 = await locations_service.create(
        session, name="Workshop", code="WS", kind="workshop", actor_user_id=None
    )
    loc2 = await locations_service.create(
        session, name="Finished Goods", code="FG", kind="finished_goods", actor_user_id=None
    )
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="X",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    return mat, loc1, loc2


@pytest.mark.asyncio
async def test_production_in_then_sale_out_accumulates(session: AsyncSession, engine) -> None:
    """production_in 5 + sale_out 2 -> on_hand row = 3."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    mat, loc, _ = await _seed(session)

    await transactions_service.record(
        session,
        kind="production_in",
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        quantity=Decimal("5"),
        actor_user_id=None,
    )
    await transactions_service.record(
        session,
        kind="sale_out",
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        quantity=Decimal("2"),
        actor_user_id=None,
    )

    rows = (await session.execute(select(InventoryOnHand))).scalars().all()
    assert len(rows) == 1
    assert rows[0].on_hand == Decimal("3.000000")


@pytest.mark.asyncio
async def test_transfer_updates_two_rows_atomically(session: AsyncSession, engine) -> None:
    """A transfer of 50 decrements source and increments destination."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    mat, src, dst = await _seed(session)

    # Seed source with 100g via production_in.
    await transactions_service.record(
        session,
        kind="production_in",
        entity_kind="material",
        entity_id=mat.id,
        location_id=src.id,
        quantity=Decimal("100"),
        actor_user_id=None,
    )
    await transactions_service.record_transfer(
        session,
        entity_kind="material",
        entity_id=mat.id,
        from_location_id=src.id,
        to_location_id=dst.id,
        quantity=Decimal("50"),
        actor_user_id=None,
    )

    rows = {
        r.location_id: r.on_hand
        for r in (await session.execute(select(InventoryOnHand))).scalars().all()
    }
    assert rows[src.id] == Decimal("50.000000")
    assert rows[dst.id] == Decimal("50.000000")
