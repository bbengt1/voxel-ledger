"""Part cost rollup: projection + breakdown + recompute (epic #267 Phase 2a)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-{uuid.uuid4().hex[:6]}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _priced_material(session: AsyncSession) -> uuid.UUID:
    """A material with a recorded receipt → current_cost_per_gram = 0.02."""
    m = await materials_service.create(
        session,
        name=f"PLA {uuid.uuid4().hex[:6]}",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await session.commit()
    await receipts_service.record(
        session,
        material_id=m.id,
        grams=Decimal("1000"),
        total_cost=Decimal("20"),  # $0.02 / g
        actor_user_id=None,
    )
    await session.commit()
    return m.id


@pytest.mark.asyncio
async def test_part_cost_breakdown_endpoint(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    material_id = await _priced_material(app_session)
    created = await client.post(
        "/api/v1/parts",
        headers=_h(owner),
        json={
            "name": "Costed",
            "print_minutes": 60,
            "parts_per_run": 1,
            "print_grams_by_material": {str(material_id): "100"},
        },
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    cost = await client.get(f"/api/v1/parts/{pid}/cost", headers=_h(owner))
    assert cost.status_code == 200, cost.text
    body = cost.json()
    # 100 g * $0.02 = $2.00 material on the single piece.
    assert Decimal(body["material_cost"]) == Decimal("2.00")
    assert Decimal(body["cost_per_piece"]) >= Decimal("2.00")


@pytest.mark.asyncio
async def test_unit_cost_cached_populated_and_recomputes_on_receipt(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    # Material with no receipt yet → cost/gram 0.
    m = await materials_service.create(
        app_session,
        name=f"PETG {uuid.uuid4().hex[:6]}",
        brand=None,
        material_type="PETG",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await app_session.commit()

    created = await client.post(
        "/api/v1/parts",
        headers=_h(owner),
        json={
            "name": "Recompute me",
            "print_minutes": 0,
            "setup_minutes": 0,
            "parts_per_run": 1,
            "print_grams_by_material": {str(m.id): "100"},
        },
    )
    pid = created.json()["id"]
    # No print time, no material cost yet → cost 0.
    assert Decimal(created.json()["unit_cost_cached"]) == Decimal("0.00")

    # Record a receipt → MaterialReceived → part_cost projection recomputes.
    await receipts_service.record(
        app_session,
        material_id=m.id,
        grams=Decimal("1000"),
        total_cost=Decimal("50"),  # $0.05 / g
        actor_user_id=None,
    )
    await app_session.commit()

    refetched = await client.get(f"/api/v1/parts/{pid}", headers=_h(owner))
    # 100 g * $0.05 = $5.00 material; cost_per_piece adds overhead + failure
    # buffer on top, so it's at least the material floor and well above 0.
    assert Decimal(refetched.json()["unit_cost_cached"]) >= Decimal("5.00")


@pytest.mark.asyncio
async def test_recompute_costs_requires_owner(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    prod = await _token(Role.PRODUCTION, client, app_session)
    forbidden = await client.post("/api/v1/parts/recompute-costs", headers=_h(prod))
    assert forbidden.status_code == 403

    owner = await _token(Role.OWNER, client, app_session)
    await client.post("/api/v1/parts", headers=_h(owner), json={"name": "P"})
    ok = await client.post("/api/v1/parts/recompute-costs", headers=_h(owner))
    assert ok.status_code == 200, ok.text
    assert ok.json()["recomputed"] >= 1
