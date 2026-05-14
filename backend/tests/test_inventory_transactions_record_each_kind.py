"""InventoryTransactionsService.record: one of each single-row kind.

Sign convention sanity check — positive kinds persist positive
quantity; negative kinds persist negative quantity; adjustment passes
through verbatim.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.inventory_transaction import (
    NEGATIVE_KINDS,
    POSITIVE_KINDS,
)
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as transactions_service
from app.services import materials as materials_service
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed(session):
    loc = await locations_service.create(
        session,
        name="Workshop",
        code="WS",
        kind="workshop",
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
    return loc, mat


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "production_in",
        "sale_out",
        "return_in",
        "waste",
        "receipt",
        "transfer_in",
        "transfer_out",
    ],
)
async def test_record_each_kind_signs_correctly(session: AsyncSession, engine, kind: str) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc, mat = await _seed(session)

    tx = await transactions_service.record(
        session,
        kind=kind,
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        quantity=Decimal("100"),
        actor_user_id=None,
    )
    await session.commit()

    if kind in POSITIVE_KINDS:
        assert tx.quantity == Decimal("100")
    elif kind in NEGATIVE_KINDS:
        assert tx.quantity == Decimal("-100")
    else:
        pytest.fail(f"kind {kind!r} should be either positive or negative")


@pytest.mark.asyncio
async def test_adjustment_passes_signed_quantity_through(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc, mat = await _seed(session)

    up = await transactions_service.record(
        session,
        kind="adjustment",
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        quantity=Decimal("5"),
        actor_user_id=None,
    )
    down = await transactions_service.record(
        session,
        kind="adjustment",
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        quantity=Decimal("-7.5"),
        actor_user_id=None,
    )
    await session.commit()

    assert up.quantity == Decimal("5")
    assert down.quantity == Decimal("-7.5")


@pytest.mark.asyncio
async def test_unit_cost_yields_total_cost(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc, mat = await _seed(session)

    tx = await transactions_service.record(
        session,
        kind="receipt",
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        quantity=Decimal("100"),
        unit_cost=Decimal("0.05"),
        actor_user_id=None,
    )
    await session.commit()
    assert tx.unit_cost_at_transaction == Decimal("0.05")
    assert tx.total_cost_at_transaction == Decimal("5.00")
