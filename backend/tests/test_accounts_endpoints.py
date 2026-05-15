"""Accounts API: role matrix + basic CRUD flows (Phase 4.1)."""

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
async def test_unauthenticated_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/accounts")
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
        "/api/v1/accounts",
        headers=_h(token),
        json={
            "code": f"1000-{role.value[:3].upper()}",
            "name": f"Cash {role.value}",
            "type": "asset",
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.BOOKKEEPER, Role.PRODUCTION, Role.SALES, Role.VIEWER],
)
async def test_list_and_tree_visible_to_every_authenticated_role(
    client: AsyncClient, app_session: AsyncSession, role: Role
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/accounts", headers=_h(token))
    assert r.status_code == 200, r.text
    r = await client.get("/api/v1/accounts/tree", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/accounts",
        headers=_h(owner),
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    aid = body["id"]
    assert body["code"] == "1000"
    assert body["type"] == "asset"
    assert body["is_archived"] is False
    assert body["parent_chain"] == []

    got = await client.get(f"/api/v1/accounts/{aid}", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["parent_chain"] == []

    patched = await client.patch(
        f"/api/v1/accounts/{aid}",
        headers=_h(owner),
        json={"name": "Total Assets"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Total Assets"

    arch = await client.post(f"/api/v1/accounts/{aid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    un = await client.post(f"/api/v1/accounts/{aid}/unarchive", headers=_h(owner))
    assert un.status_code == 200
    assert un.json()["is_archived"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_archive_owner_only(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/accounts",
        headers=_h(owner),
        json={"code": f"A{role.value[:3].upper()}", "name": "X", "type": "asset"},
    )
    aid = create.json()["id"]
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/accounts/{aid}/archive", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_patch_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/accounts",
        headers=_h(owner),
        json={"code": f"P{role.value[:3].upper()}", "name": "X", "type": "asset"},
    )
    aid = create.json()["id"]
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.patch(
        f"/api/v1/accounts/{aid}",
        headers=_h(token),
        json={"name": "renamed"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_list_search_type_archived_filters(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    for code, name, typ in [
        ("1000", "Assets", "asset"),
        ("2000", "Liabilities", "liability"),
        ("4000", "Revenue", "revenue"),
    ]:
        await client.post(
            "/api/v1/accounts",
            headers=_h(owner),
            json={"code": code, "name": name, "type": typ},
        )

    r = await client.get("/api/v1/accounts?search=assets", headers=_h(owner))
    assert [it["code"] for it in r.json()["items"]] == ["1000"]

    r = await client.get("/api/v1/accounts?type=revenue", headers=_h(owner))
    assert [it["code"] for it in r.json()["items"]] == ["4000"]

    items = (await client.get("/api/v1/accounts", headers=_h(owner))).json()["items"]
    aid = next(it["id"] for it in items if it["code"] == "2000")
    await client.post(f"/api/v1/accounts/{aid}/archive", headers=_h(owner))
    r = await client.get("/api/v1/accounts?is_archived=true", headers=_h(owner))
    assert [it["code"] for it in r.json()["items"]] == ["2000"]


@pytest.mark.asyncio
async def test_get_includes_parent_chain(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    a = await client.post(
        "/api/v1/accounts",
        headers=_h(owner),
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    aid = a.json()["id"]
    b = await client.post(
        "/api/v1/accounts",
        headers=_h(owner),
        json={"code": "1100", "name": "Current", "type": "asset", "parent_account_id": aid},
    )
    bid = b.json()["id"]
    c = await client.post(
        "/api/v1/accounts",
        headers=_h(owner),
        json={"code": "1110", "name": "Cash", "type": "asset", "parent_account_id": bid},
    )
    cid = c.json()["id"]
    got = await client.get(f"/api/v1/accounts/{cid}", headers=_h(owner))
    chain = got.json()["parent_chain"]
    assert [item["code"] for item in chain] == ["1000", "1100"]


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/accounts/00000000-0000-0000-0000-000000000000",
        headers=_h(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/accounts" in paths
    assert "/api/v1/accounts/tree" in paths
    assert "/api/v1/accounts/{account_id}" in paths
    assert "/api/v1/accounts/{account_id}/archive" in paths
    assert "/api/v1/accounts/{account_id}/unarchive" in paths
