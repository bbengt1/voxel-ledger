"""Printers API: role matrix + happy paths."""

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
    r = await client.get("/api/v1/printers")
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
        "/api/v1/printers",
        headers=_h(token),
        json={
            "name": f"Printer {role.value}",
            "slug": f"prn-{role.value}",
            "printer_type": "prusa_mk4",
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
    r = await client.get("/api/v1/printers", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/printers",
        headers=_h(owner),
        json={
            "name": "Voron #1",
            "slug": "voron-1",
            "printer_type": "voron_v2_4",
            "moonraker_url": "http://10.0.0.10:7125",
            "power_draw_watts": 350,
            "notes": "Workshop bench.",
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    pid = body["id"]
    assert body["slug"] == "voron-1"
    assert body["printer_type"] == "voron_v2_4"
    assert body["is_archived"] is False
    assert body["moonraker_api_key_set"] is False
    assert "moonraker_api_key" not in body

    got = await client.get(f"/api/v1/printers/{pid}", headers=_h(owner))
    assert got.status_code == 200

    patched = await client.patch(
        f"/api/v1/printers/{pid}",
        headers=_h(owner),
        json={"name": "Voron #1 (main)", "power_draw_watts": 400},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Voron #1 (main)"
    assert patched.json()["power_draw_watts"] == 400

    arch = await client.post(f"/api/v1/printers/{pid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    un = await client.post(f"/api/v1/printers/{pid}/unarchive", headers=_h(owner))
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
        "/api/v1/printers",
        headers=_h(owner),
        json={
            "name": f"P-{role.value}",
            "slug": f"p-{role.value}",
            "printer_type": "other",
        },
    )
    pid = create.json()["id"]

    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/printers/{pid}/archive", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_create_duplicate_active_slug_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    body = {"name": "P1", "slug": "dup", "printer_type": "other"}
    r1 = await client.post("/api/v1/printers", headers=_h(owner), json=body)
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/printers",
        headers=_h(owner),
        json={**body, "name": "P2"},
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/printers/00000000-0000-0000-0000-000000000000",
        headers=_h(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/printers" in paths
    assert "/api/v1/printers/{printer_id}" in paths
    assert "/api/v1/printers/{printer_id}/archive" in paths
    assert "/api/v1/printers/{printer_id}/unarchive" in paths
    assert "/api/v1/printers/{printer_id}/cameras" in paths
    assert "/api/v1/printers/{printer_id}/cameras/snapshot.jpg" in paths
