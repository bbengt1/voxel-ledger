"""Transfers: pair_id is shared; same-location rejected; missing destination rolls back."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models import Base
from app.models.inventory_transaction import InventoryTransaction
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as transactions_service
from app.services import materials as materials_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_pair(session):
    a = await locations_service.create(
        session, name="A", code="A", kind="workshop", actor_user_id=None
    )
    b = await locations_service.create(
        session, name="B", code="B", kind="staging", actor_user_id=None
    )
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    return a, b, mat


@pytest.mark.asyncio
async def test_transfer_creates_two_rows_with_shared_pair(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    a, b, mat = await _seed_pair(session)

    out_tx, in_tx = await transactions_service.record_transfer(
        session,
        entity_kind="material",
        entity_id=mat.id,
        from_location_id=a.id,
        to_location_id=b.id,
        quantity=Decimal("250"),
        actor_user_id=None,
    )
    await session.commit()

    assert out_tx.kind == "transfer_out"
    assert in_tx.kind == "transfer_in"
    assert out_tx.location_id == a.id
    assert in_tx.location_id == b.id
    assert out_tx.quantity == Decimal("-250")
    assert in_tx.quantity == Decimal("250")
    assert out_tx.transfer_pair_id == in_tx.transfer_pair_id
    assert out_tx.transfer_pair_id is not None


@pytest.mark.asyncio
async def test_transfer_rejects_same_location(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    a, _b, mat = await _seed_pair(session)
    with pytest.raises(transactions_service.TransferLocationsError):
        await transactions_service.record_transfer(
            session,
            entity_kind="material",
            entity_id=mat.id,
            from_location_id=a.id,
            to_location_id=a.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_transfer_rolls_back_when_dest_missing(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    a, _b, mat = await _seed_pair(session)
    missing = uuid.uuid4()

    with pytest.raises(transactions_service.LocationNotFoundError):
        await transactions_service.record_transfer(
            session,
            entity_kind="material",
            entity_id=mat.id,
            from_location_id=a.id,
            to_location_id=missing,
            quantity=Decimal("5"),
            actor_user_id=None,
        )
    # The session is poisoned by the failed transfer; roll back so we
    # can query a fresh state.
    await session.rollback()

    rows = (await session.execute(select(InventoryTransaction))).scalars().all()
    assert rows == []
