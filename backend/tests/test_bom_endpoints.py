"""BOM endpoints: role matrix + happy paths."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services import materials as materials_service
from app.services import products as products_service
from app.services import supplies as supplies_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed(client: AsyncClient, app_session: AsyncSession):
    """Returns (owner_token, product_id, material_id, supply_id)."""
    owner = await _token_for(Role.OWNER, client, app_session)

    p = await products_service.create(
        app_session,
        name="Parent",
        description=None,
        unit_price=Decimal("10"),
        actor_user_id=None,
    )
    m = await materials_service.create(
        app_session,
        name="PLA-A",
        brand="X",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    s = await supplies_service.create(
        app_session,
        name="Bag",
        unit="ea",
        unit_cost=Decimal("0.50"),
        vendor=None,
        actor_user_id=None,
    )
    await app_session.commit()
    return owner, p.id, m.id, s.id


@pytest.mark.asyncio
async def test_unauthenticated_get_bom_401(client: AsyncClient) -> None:
    import uuid

    r = await client.get(f"/api/v1/products/{uuid.uuid4()}/bom")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.SALES, 403),
        (Role.BOOKKEEPER, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_add_component_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner, pid, mid, _sid = await _seed(client, app_session)
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(
        f"/api/v1/products/{pid}/bom",
        headers=_h(token),
        json={
            "component_kind": "material",
            "component_id": str(mid),
            "quantity": "100",
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.BOOKKEEPER, Role.PRODUCTION, Role.SALES, Role.VIEWER],
)
async def test_list_bom_visible_to_every_authenticated_role(
    client: AsyncClient, app_session: AsyncSession, role: Role
) -> None:
    owner, pid, _mid, _sid = await _seed(client, app_session)
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.get(f"/api/v1/products/{pid}/bom", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_update_delete_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner, pid, mid, sid = await _seed(client, app_session)

    # Add a material component.
    r = await client.post(
        f"/api/v1/products/{pid}/bom",
        headers=_h(owner),
        json={"component_kind": "material", "component_id": str(mid), "quantity": "100"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    item_id = body["id"]
    assert body["component_kind"] == "material"
    # Material has zero cost initially (no receipts), so resolved_unit_cost
    # is 0 — but it's not None.
    assert body["resolved_unit_cost"] is not None

    # Add a supply component.
    r2 = await client.post(
        f"/api/v1/products/{pid}/bom",
        headers=_h(owner),
        json={"component_kind": "supply", "component_id": str(sid), "quantity": "2"},
    )
    assert r2.status_code == 201
    assert Decimal(r2.json()["line_cost"]) == Decimal("1.000000")

    # List.
    listing = await client.get(f"/api/v1/products/{pid}/bom", headers=_h(owner))
    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 2

    # PATCH quantity.
    patch = await client.patch(
        f"/api/v1/products/{pid}/bom/{item_id}",
        headers=_h(owner),
        json={"quantity": "200"},
    )
    assert patch.status_code == 200
    assert Decimal(patch.json()["quantity"]) == Decimal("200")

    # DELETE.
    deletion = await client.delete(f"/api/v1/products/{pid}/bom/{item_id}", headers=_h(owner))
    assert deletion.status_code == 204

    listing2 = await client.get(f"/api/v1/products/{pid}/bom", headers=_h(owner))
    assert len(listing2.json()["items"]) == 1


@pytest.mark.asyncio
async def test_cost_breakdown_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    owner, pid, _mid, sid = await _seed(client, app_session)
    await client.post(
        f"/api/v1/products/{pid}/bom",
        headers=_h(owner),
        json={"component_kind": "supply", "component_id": str(sid), "quantity": "3"},
    )
    r = await client.get(f"/api/v1/products/{pid}/cost-breakdown", headers=_h(owner))
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == str(pid)
    assert len(body["components"]) == 1
    assert Decimal(body["total_cost"]) == Decimal("1.500000")


@pytest.mark.asyncio
async def test_get_404_for_missing_product(client: AsyncClient, app_session: AsyncSession) -> None:
    import uuid

    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(f"/api/v1/products/{uuid.uuid4()}/bom", headers=_h(owner))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/products/{product_id}/bom" in paths
    assert "/api/v1/products/{product_id}/bom/{bom_item_id}" in paths
    assert "/api/v1/products/{product_id}/cost-breakdown" in paths
