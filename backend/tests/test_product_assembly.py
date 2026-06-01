"""Product assembly: assembly labor + material rollup + kind rejection
(assembly-line epic #267 Phase 3a)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services import parts as parts_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-{uuid.uuid4().hex[:6]}@example.com"
    await create_user(
        session, email=email, password="pw", full_name="t", role=role, bcrypt_rounds=4
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_assembly_labor_added_and_recomputes_on_change(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    # Part with no recipe → cost 0.00.
    part = await parts_service.create(app_session, name="Body", actor_user_id=None)
    await app_session.commit()

    created = await client.post(
        "/api/v1/products",
        headers=_h(owner),
        json={
            "name": "Assembled",
            "unit_price": "10",
            "assembly_minutes": 0,
            "bom_items": [
                {"component_kind": "part", "component_id": str(part.id), "quantity": "1"}
            ],
        },
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    # Part cost 0 + no assembly labor → 0.00.
    assert Decimal(created.json()["unit_cost_cached"]) == Decimal("0.00")

    # Add assembly labor → product cost increases (ProductUpdated → recompute).
    patched = await client.patch(
        f"/api/v1/products/{pid}", headers=_h(owner), json={"assembly_minutes": 60}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["assembly_minutes"] == 60

    got = await client.get(f"/api/v1/products/{pid}", headers=_h(owner))
    assert Decimal(got.json()["unit_cost_cached"]) > Decimal("0.00")

    # Remove it again → back to 0.
    await client.patch(f"/api/v1/products/{pid}", headers=_h(owner), json={"assembly_minutes": 0})
    back = await client.get(f"/api/v1/products/{pid}", headers=_h(owner))
    assert Decimal(back.json()["unit_cost_cached"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_material_rollup_from_parts(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    material_id = uuid.uuid4()
    # Part prints 100 g of the material per run, 2 parts/run.
    part = await parts_service.create(
        app_session,
        name="Geared",
        parts_per_run=2,
        print_grams_by_material={material_id: Decimal("100")},
        actor_user_id=None,
    )
    await app_session.commit()

    created = await client.post(
        "/api/v1/products",
        headers=_h(owner),
        json={
            "name": "Gearbox",
            "unit_price": "10",
            "bom_items": [
                {"component_kind": "part", "component_id": str(part.id), "quantity": "3"}
            ],
        },
    )
    pid = created.json()["id"]

    r = await client.get(f"/api/v1/products/{pid}/materials", headers=_h(owner))
    assert r.status_code == 200, r.text
    # 3 parts x (100 g / 2 per run) = 150 g.
    assert Decimal(r.json()["materials"][str(material_id)]) == Decimal("150.000000")


@pytest.mark.asyncio
async def test_product_bom_rejects_material_kind(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    created = await client.post(
        "/api/v1/products", headers=_h(owner), json={"name": "P", "unit_price": "1"}
    )
    pid = created.json()["id"]
    r = await client.post(
        f"/api/v1/products/{pid}/bom",
        headers=_h(owner),
        json={"component_kind": "material", "component_id": str(uuid.uuid4()), "quantity": "1"},
    )
    # Service rejects material on a product BOM → 400.
    assert r.status_code == 400, r.text
