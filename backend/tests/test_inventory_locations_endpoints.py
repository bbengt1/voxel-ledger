"""Inventory locations API: role matrix + happy paths."""

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
    r = await client.get("/api/v1/inventory/locations")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(token),
        json={
            "name": f"Workshop {role.value}",
            "code": f"W-{role.value[:3].upper()}",
            "kind": "workshop",
        },
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
    r = await client.get("/api/v1/inventory/locations", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(owner),
        json={
            "name": "Workshop bench",
            "code": "WSB",
            "kind": "workshop",
            "description": "Main bench in the workshop",
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    lid = body["id"]
    assert body["name"] == "Workshop bench"
    assert body["code"] == "WSB"
    assert body["kind"] == "workshop"
    assert body["is_archived"] is False

    got = await client.get(f"/api/v1/inventory/locations/{lid}", headers=_h(owner))
    assert got.status_code == 200

    patched = await client.patch(
        f"/api/v1/inventory/locations/{lid}",
        headers=_h(owner),
        json={"name": "Workshop bench (main)", "kind": "staging"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Workshop bench (main)"
    assert patched.json()["kind"] == "staging"

    arch = await client.post(f"/api/v1/inventory/locations/{lid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    un = await client.post(f"/api/v1/inventory/locations/{lid}/unarchive", headers=_h(owner))
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
        "/api/v1/inventory/locations",
        headers=_h(owner),
        json={"name": f"Loc-{role.value}", "code": f"L{role.value[:3].upper()}", "kind": "virtual"},
    )
    lid = create.json()["id"]

    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/inventory/locations/{lid}/archive", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.PRODUCTION, 200),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_patch_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(owner),
        json={"name": f"Loc-{role.value}", "code": f"P{role.value[:3].upper()}", "kind": "virtual"},
    )
    lid = create.json()["id"]
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.patch(
        f"/api/v1/inventory/locations/{lid}",
        headers=_h(token),
        json={"name": "renamed"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_list_search_kind_archived_filters(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    for name, code, kind in [
        ("Workshop bench", "WSB", "workshop"),
        ("Finished goods", "FG", "finished_goods"),
        ("Staging cart", "STG", "staging"),
    ]:
        await client.post(
            "/api/v1/inventory/locations",
            headers=_h(owner),
            json={"name": name, "code": code, "kind": kind},
        )
    r = await client.get("/api/v1/inventory/locations?search=workshop", headers=_h(owner))
    assert r.status_code == 200
    assert [item["code"] for item in r.json()["items"]] == ["WSB"]

    r = await client.get("/api/v1/inventory/locations?kind=finished_goods", headers=_h(owner))
    assert [item["code"] for item in r.json()["items"]] == ["FG"]

    # Archive one then filter.
    fg_id = next(
        item["id"]
        for item in (await client.get("/api/v1/inventory/locations", headers=_h(owner))).json()[
            "items"
        ]
        if item["code"] == "FG"
    )
    await client.post(f"/api/v1/inventory/locations/{fg_id}/archive", headers=_h(owner))
    r = await client.get("/api/v1/inventory/locations?is_archived=true", headers=_h(owner))
    assert [item["code"] for item in r.json()["items"]] == ["FG"]


@pytest.mark.asyncio
async def test_create_duplicate_active_code_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    body = {"name": "Workshop", "code": "WS", "kind": "workshop"}
    r1 = await client.post("/api/v1/inventory/locations", headers=_h(owner), json=body)
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(owner),
        json={**body, "name": "Workshop 2"},
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/inventory/locations/00000000-0000-0000-0000-000000000000",
        headers=_h(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/inventory/locations" in paths
    assert "/api/v1/inventory/locations/{location_id}" in paths
    assert "/api/v1/inventory/locations/{location_id}/archive" in paths
    assert "/api/v1/inventory/locations/{location_id}/unarchive" in paths
