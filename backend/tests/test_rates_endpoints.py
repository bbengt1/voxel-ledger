"""Rates API: role matrix + list by kind + set-default flow."""

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
    r = await client.get("/api/v1/rates")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 403),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix_owner_only(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/rates",
        headers=_h(token),
        json={"name": f"Labor {role.value}", "kind": "labor", "value": "25.00"},
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
    r = await client.get("/api/v1/rates", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_list_kind_filter(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={"name": "Labor base", "kind": "labor", "value": "25.00"},
    )
    await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={"name": "Machine FDM", "kind": "machine", "value": "5.00"},
    )
    await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={"name": "Overhead", "kind": "overhead", "value": "0.15"},
    )

    r = await client.get("/api/v1/rates?kind=labor", headers=_h(owner))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "labor"


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={"name": "Standard labor", "kind": "labor", "value": "25.00"},
    )
    assert create.status_code == 201, create.text
    rid = create.json()["id"]

    got = await client.get(f"/api/v1/rates/{rid}", headers=_h(owner))
    assert got.status_code == 200

    patched = await client.patch(
        f"/api/v1/rates/{rid}",
        headers=_h(owner),
        json={"value": "27.50"},
    )
    assert patched.status_code == 200
    from decimal import Decimal as _D

    assert _D(patched.json()["value"]) == _D("27.50")

    arch = await client.post(f"/api/v1/rates/{rid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    un = await client.post(f"/api/v1/rates/{rid}/unarchive", headers=_h(owner))
    assert un.status_code == 200
    assert un.json()["is_archived"] is False


@pytest.mark.asyncio
async def test_set_default_endpoint_flips_atomically(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    a = await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={
            "name": "Labor A",
            "kind": "labor",
            "value": "25.00",
            "is_default_for_kind": True,
        },
    )
    b = await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={"name": "Labor B", "kind": "labor", "value": "30.00"},
    )
    aid = a.json()["id"]
    bid = b.json()["id"]

    r = await client.post(f"/api/v1/rates/{bid}/set-default", headers=_h(owner))
    assert r.status_code == 200, r.text
    assert r.json()["is_default_for_kind"] is True

    again = await client.get(f"/api/v1/rates/{aid}", headers=_h(owner))
    assert again.json()["is_default_for_kind"] is False


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
async def test_set_default_owner_only(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={"name": f"Labor-{role.value}", "kind": "labor", "value": "25"},
    )
    rid = create.json()["id"]

    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/rates/{rid}/set-default", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/rates" in paths
    assert "/api/v1/rates/{rate_id}" in paths
    assert "/api/v1/rates/{rate_id}/set-default" in paths
    assert "/api/v1/rates/{rate_id}/archive" in paths
    assert "/api/v1/rates/{rate_id}/unarchive" in paths
