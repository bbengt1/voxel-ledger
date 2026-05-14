"""Products API: role matrix + happy paths."""

from __future__ import annotations

import pytest
from app.models.auth import Role
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


@pytest.mark.asyncio
async def test_unauthenticated_get_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/products")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.SALES, 201),
        (Role.BOOKKEEPER, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/products",
        headers=_h(token),
        json={"name": f"Widget {role.value}", "unit_price": "9.99"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.BOOKKEEPER, Role.PRODUCTION, Role.SALES, Role.VIEWER],
)
async def test_list_visible_to_every_authenticated_role(
    client: AsyncClient, app_session: AsyncSession, role: Role
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/products", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/products",
        headers=_h(owner),
        json={
            "name": "Standard Widget",
            "description": "a widget",
            "unit_price": "12.50",
            "category": "widgets",
            "weight_grams": "42",
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    pid = body["id"]
    assert body["sku"].startswith("PROD-")
    # unit_cost_cached is null until BOM exists (Phase 2.4).
    assert body["unit_cost_cached"] is None

    # GET
    got = await client.get(f"/api/v1/products/{pid}", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["name"] == "Standard Widget"

    # PATCH name
    patched = await client.patch(
        f"/api/v1/products/{pid}",
        headers=_h(owner),
        json={"name": "Standard Widget Pro"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Standard Widget Pro"

    # Archive (owner-only)
    arch = await client.post(f"/api/v1/products/{pid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    # Unarchive
    un = await client.post(f"/api/v1/products/{pid}/unarchive", headers=_h(owner))
    assert un.status_code == 200
    assert un.json()["is_archived"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.PRODUCTION, 403),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_archive_owner_only(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/products",
        headers=_h(owner),
        json={"name": "Widget", "unit_price": "1.00"},
    )
    pid = create.json()["id"]
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/products/{pid}/archive", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_lookup_by_sku_and_upc(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/products",
        headers=_h(owner),
        json={
            "name": "Scan Me",
            "unit_price": "5.00",
            "sku": "SCAN-001",
            "upc": "012345678905",
        },
    )
    pid = create.json()["id"]

    r = await client.get("/api/v1/products/lookup", headers=_h(owner), params={"code": "SCAN-001"})
    assert r.status_code == 200
    assert r.json()["id"] == pid

    r = await client.get(
        "/api/v1/products/lookup", headers=_h(owner), params={"code": "012345678905"}
    )
    assert r.status_code == 200
    assert r.json()["id"] == pid

    r = await client.get("/api/v1/products/lookup", headers=_h(owner), params={"code": "MISSING"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_search_category_and_archived_filter(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    for name, cat in [("Red Thing", "things"), ("Blue Thing", "things"), ("Gadget", "gadgets")]:
        await client.post(
            "/api/v1/products",
            headers=_h(owner),
            json={"name": name, "unit_price": "1.00", "category": cat},
        )
    r = await client.get("/api/v1/products?search=red", headers=_h(owner))
    assert r.status_code == 200
    assert [m["name"] for m in r.json()["items"]] == ["Red Thing"]

    r = await client.get("/api/v1/products?category=gadgets", headers=_h(owner))
    assert [m["name"] for m in r.json()["items"]] == ["Gadget"]


@pytest.mark.asyncio
async def test_duplicate_sku_returns_400(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    body = {"name": "W", "unit_price": "1.00", "sku": "DUP-1"}
    r1 = await client.post("/api/v1/products", headers=_h(owner), json=body)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/products", headers=_h(owner), json=body)
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/products" in paths
    assert "/api/v1/products/lookup" in paths
    assert "/api/v1/products/{product_id}" in paths
    assert "/api/v1/products/{product_id}/archive" in paths
    assert "/api/v1/products/{product_id}/unarchive" in paths
