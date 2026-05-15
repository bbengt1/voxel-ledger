"""Divisions API: role matrix + basic CRUD flows (Phase 4.5)."""

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
    r = await client.get("/api/v1/accounting/divisions")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_owner_only(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/accounting/divisions",
        headers=_h(token),
        json={"name": f"D-{role.value}", "code": f"D{role.value[:3].upper()}"},
    )
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
async def test_list_owner_and_bookkeeper(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/accounting/divisions", headers=_h(token))
    assert r.status_code == expected


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/accounting/divisions",
        headers=_h(owner),
        json={"name": "3D Printing", "code": "3DP"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    did = body["id"]
    assert body["code"] == "3DP"
    assert body["is_archived"] is False

    got = await client.get(f"/api/v1/accounting/divisions/{did}", headers=_h(owner))
    assert got.status_code == 200

    patched = await client.patch(
        f"/api/v1/accounting/divisions/{did}",
        headers=_h(owner),
        json={"name": "Production"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Production"

    arch = await client.post(f"/api/v1/accounting/divisions/{did}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    un = await client.post(f"/api/v1/accounting/divisions/{did}/unarchive", headers=_h(owner))
    assert un.status_code == 200
    assert un.json()["is_archived"] is False


@pytest.mark.asyncio
async def test_patch_code_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/accounting/divisions",
        headers=_h(owner),
        json={"name": "D", "code": "DIV"},
    )
    did = create.json()["id"]
    r = await client.patch(
        f"/api/v1/accounting/divisions/{did}",
        headers=_h(owner),
        json={"code": "NEW"},
    )
    # Pydantic schema strips ``code`` (it's not in DivisionUpdateRequest)
    # so this is a no-op happy path 200; verify the code wasn't changed.
    assert r.status_code in (200, 400, 422)
    got = await client.get(f"/api/v1/accounting/divisions/{did}", headers=_h(owner))
    assert got.json()["code"] == "DIV"


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/accounting/divisions/00000000-0000-0000-0000-000000000000",
        headers=_h(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_active_code_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r1 = await client.post(
        "/api/v1/accounting/divisions",
        headers=_h(owner),
        json={"name": "A", "code": "DUP"},
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/accounting/divisions",
        headers=_h(owner),
        json={"name": "B", "code": "DUP"},
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/accounting/divisions" in paths
    assert "/api/v1/accounting/divisions/{division_id}" in paths
    assert "/api/v1/accounting/divisions/{division_id}/archive" in paths
