"""Caller-supplied negative magnitudes are rejected for non-adjustment kinds."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as transactions_service
from app.services import materials as materials_service
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed(session):
    loc = await locations_service.create(
        session,
        name="WS",
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
@pytest.mark.parametrize("kind", ["production_in", "sale_out", "return_in", "waste", "receipt"])
async def test_negative_magnitude_rejected(session: AsyncSession, engine, kind: str) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc, mat = await _seed(session)

    with pytest.raises(transactions_service.InventoryQuantityError):
        await transactions_service.record(
            session,
            kind=kind,
            entity_kind="material",
            entity_id=mat.id,
            location_id=loc.id,
            quantity=Decimal("-1"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_zero_quantity_rejected(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    loc, mat = await _seed(session)
    with pytest.raises(transactions_service.InventoryQuantityError):
        await transactions_service.record(
            session,
            kind="production_in",
            entity_kind="material",
            entity_id=mat.id,
            location_id=loc.id,
            quantity=Decimal("0"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_endpoint_returns_400_for_negative(client, app_session) -> None:
    from app.models.auth import Role
    from app.services.auth import create_user

    await create_user(
        app_session,
        email="o@example.com",
        password="pw-correct",
        full_name="O",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    tok = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "o@example.com", "password": "pw-correct"},
        )
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    loc = (
        await client.post(
            "/api/v1/inventory/locations",
            headers=h,
            json={"name": "WS", "code": "WS", "kind": "workshop"},
        )
    ).json()
    mat = (
        await client.post(
            "/api/v1/materials",
            headers=h,
            json={"name": "PLA", "brand": "A", "material_type": "PLA"},
        )
    ).json()
    r = await client.post(
        "/api/v1/inventory/transactions",
        headers=h,
        json={
            "kind": "production_in",
            "entity_kind": "material",
            "entity_id": mat["id"],
            "location_id": loc["id"],
            "quantity": "-3",
        },
    )
    assert r.status_code == 400, r.text
    assert "magnitude must be positive" in r.json()["detail"]
