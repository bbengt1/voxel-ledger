"""Sales channels API: role matrix, CRUD, archive/unarchive, ?active filter."""

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


def _shopify_body(name: str = "Shopify", slug: str = "shopify") -> dict:
    return {
        "name": name,
        "slug": slug,
        "kind": "direct_web",
        "fee_model": "percent_plus_flat",
        "fee_percent": "0.0290",
        "fee_flat": "0.30",
        "external_id_format_hint": "^SHOP-\\d{10}$",
    }


# ---------------------------------------------------------------------------
# Auth / role matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/sales-channels")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 201),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/sales-channels",
        headers=_h(token),
        json=_shopify_body(name=f"Shop {role.value}", slug=f"shop-{role.value}"),
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.SALES, 200),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_list_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/sales-channels", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.SALES, 403),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_archive_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales-channels",
        headers=_h(owner),
        json=_shopify_body(name=f"Ch-{role.value}", slug=f"ch-{role.value}"),
    )
    cid = create.json()["id"]
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/sales-channels/{cid}/archive", headers=_h(token))
    assert r.status_code == expected, r.text


# ---------------------------------------------------------------------------
# Happy-path CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post("/api/v1/sales-channels", headers=_h(owner), json=_shopify_body())
    assert create.status_code == 201, create.text
    body = create.json()
    cid = body["id"]
    assert body["name"] == "Shopify"
    assert body["slug"] == "shopify"
    assert body["kind"] == "direct_web"
    assert body["fee_model"] == "percent_plus_flat"
    assert body["fee_percent"] == "0.0290"
    assert body["fee_flat"] == "0.30"
    assert body["is_active"] is True

    got = await client.get(f"/api/v1/sales-channels/{cid}", headers=_h(owner))
    assert got.status_code == 200

    patched = await client.patch(
        f"/api/v1/sales-channels/{cid}",
        headers=_h(owner),
        json={"fee_percent": "0.0349", "name": "Shopify Plus"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["fee_percent"] == "0.0349"
    assert patched.json()["name"] == "Shopify Plus"

    arch = await client.post(f"/api/v1/sales-channels/{cid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_active"] is False

    un = await client.post(f"/api/v1/sales-channels/{cid}/unarchive", headers=_h(owner))
    assert un.status_code == 200
    assert un.json()["is_active"] is True


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/sales-channels/00000000-0000-0000-0000-000000000000",
        headers=_h(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_name_or_slug_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r1 = await client.post("/api/v1/sales-channels", headers=_h(owner), json=_shopify_body())
    assert r1.status_code == 201
    # same name, different slug
    r2 = await client.post(
        "/api/v1/sales-channels",
        headers=_h(owner),
        json=_shopify_body(slug="shopify-2"),
    )
    assert r2.status_code == 400
    # same slug, different name
    r3 = await client.post(
        "/api/v1/sales-channels",
        headers=_h(owner),
        json=_shopify_body(name="Other"),
    )
    assert r3.status_code == 400


@pytest.mark.asyncio
async def test_invalid_fee_config_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    # percent_plus_flat without fee_flat
    r = await client.post(
        "/api/v1/sales-channels",
        headers=_h(owner),
        json={
            "name": "Bad",
            "slug": "bad",
            "kind": "marketplace",
            "fee_model": "percent_plus_flat",
            "fee_percent": "0.05",
        },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_active_filter(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    a = await client.post(
        "/api/v1/sales-channels",
        headers=_h(owner),
        json={
            "name": "Retail",
            "slug": "retail",
            "kind": "pos",
            "fee_model": "none",
        },
    )
    b = await client.post(
        "/api/v1/sales-channels",
        headers=_h(owner),
        json={
            "name": "Etsy",
            "slug": "etsy",
            "kind": "marketplace",
            "fee_model": "percent",
            "fee_percent": "0.065",
        },
    )
    assert a.status_code == 201 and b.status_code == 201
    bid = b.json()["id"]
    await client.post(f"/api/v1/sales-channels/{bid}/archive", headers=_h(owner))

    only_active = await client.get("/api/v1/sales-channels?active=true", headers=_h(owner))
    slugs = {item["slug"] for item in only_active.json()["items"]}
    assert slugs == {"retail"}

    only_inactive = await client.get("/api/v1/sales-channels?active=false", headers=_h(owner))
    slugs = {item["slug"] for item in only_inactive.json()["items"]}
    assert slugs == {"etsy"}

    all_rows = await client.get("/api/v1/sales-channels", headers=_h(owner))
    slugs = {item["slug"] for item in all_rows.json()["items"]}
    assert slugs == {"retail", "etsy"}


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/sales-channels" in paths
    assert "/api/v1/sales-channels/{channel_id}" in paths
    assert "/api/v1/sales-channels/{channel_id}/archive" in paths
    assert "/api/v1/sales-channels/{channel_id}/unarchive" in paths
