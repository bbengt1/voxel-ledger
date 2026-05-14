"""Polymorphic entity validation: wrong table → 404; archived → 400."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models import Base
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as transactions_service
from app.services import materials as materials_service
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_loc(session):
    return await locations_service.create(
        session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )


@pytest.mark.asyncio
async def test_unknown_entity_id_raises_not_found(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc = await _seed_loc(session)
    with pytest.raises(transactions_service.EntityNotFoundError):
        await transactions_service.record(
            session,
            kind="production_in",
            entity_kind="material",
            entity_id=uuid.uuid4(),
            location_id=loc.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_product_id_under_material_kind_404(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc = await _seed_loc(session)
    product = await products_service.create(
        session,
        sku="P-1",
        name="Widget",
        description=None,
        unit_price=Decimal("9.99"),
        actor_user_id=None,
    )
    # Passing a product UUID under entity_kind=material must not resolve.
    with pytest.raises(transactions_service.EntityNotFoundError):
        await transactions_service.record(
            session,
            kind="production_in",
            entity_kind="material",
            entity_id=product.id,
            location_id=loc.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_archived_entity_rejected(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc = await _seed_loc(session)
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    await materials_service.archive(session, material_id=mat.id, actor_user_id=None)
    with pytest.raises(transactions_service.EntityArchivedError):
        await transactions_service.record(
            session,
            kind="production_in",
            entity_kind="material",
            entity_id=mat.id,
            location_id=loc.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_archived_location_rejected(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc = await _seed_loc(session)
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    await locations_service.archive(session, location_id=loc.id, actor_user_id=None)
    with pytest.raises(transactions_service.LocationArchivedError):
        await transactions_service.record(
            session,
            kind="production_in",
            entity_kind="material",
            entity_id=mat.id,
            location_id=loc.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
