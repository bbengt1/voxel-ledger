"""Accounting-periods API: role matrix + happy path (Phase 4.3, #66)."""

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


_BODY = {
    "name": "2026-Q1",
    "start_date": "2026-01-01",
    "end_date": "2026-03-31",
}


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
    body = {"name": f"p-{role.value}", "start_date": "1900-01-01", "end_date": "1900-01-31"}
    r = await client.post("/api/v1/accounting/periods", headers=_h(token), json=body)
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_list_get_visible_to_every_authenticated(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    viewer = await _token_for(Role.VIEWER, client, app_session)
    created = await client.post("/api/v1/accounting/periods", headers=_h(owner), json=_BODY)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    lst = await client.get("/api/v1/accounting/periods", headers=_h(viewer))
    assert lst.status_code == 200
    assert any(item["id"] == pid for item in lst.json()["items"])

    one = await client.get(f"/api/v1/accounting/periods/{pid}", headers=_h(viewer))
    assert one.status_code == 200


@pytest.mark.asyncio
async def test_overlap_returns_400(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    a = await client.post("/api/v1/accounting/periods", headers=_h(owner), json=_BODY)
    assert a.status_code == 201
    dup = await client.post(
        "/api/v1/accounting/periods",
        headers=_h(owner),
        json={
            "name": "dup",
            "start_date": "2026-02-01",
            "end_date": "2026-04-30",
        },
    )
    assert dup.status_code == 400


@pytest.mark.asyncio
async def test_lock_endpoint_owner_only(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    bookkeeper = await _token_for(Role.BOOKKEEPER, client, app_session)
    created = await client.post("/api/v1/accounting/periods", headers=_h(owner), json=_BODY)
    pid = created.json()["id"]
    # Close first (both roles can close).
    closed = await client.post(f"/api/v1/accounting/periods/{pid}/close", headers=_h(bookkeeper))
    assert closed.status_code == 200
    # Bookkeeper can NOT lock.
    fail = await client.post(f"/api/v1/accounting/periods/{pid}/lock", headers=_h(bookkeeper))
    assert fail.status_code == 403
    # Owner can lock.
    ok = await client.post(f"/api/v1/accounting/periods/{pid}/lock", headers=_h(owner))
    assert ok.status_code == 200
    assert ok.json()["state"] == "locked"


@pytest.mark.asyncio
async def test_close_reopen_round_trip(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    created = await client.post("/api/v1/accounting/periods", headers=_h(owner), json=_BODY)
    pid = created.json()["id"]
    await client.post(f"/api/v1/accounting/periods/{pid}/close", headers=_h(owner))
    reopened = await client.post(f"/api/v1/accounting/periods/{pid}/reopen", headers=_h(owner))
    assert reopened.status_code == 200
    assert reopened.json()["state"] == "open"


@pytest.mark.asyncio
async def test_patch_renames(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    created = await client.post("/api/v1/accounting/periods", headers=_h(owner), json=_BODY)
    pid = created.json()["id"]
    r = await client.patch(
        f"/api/v1/accounting/periods/{pid}",
        headers=_h(owner),
        json={"name": "renamed"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "renamed"


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/accounting/periods" in paths
    assert "/api/v1/accounting/periods/{period_id}" in paths
    assert "/api/v1/accounting/periods/{period_id}/close" in paths
    assert "/api/v1/accounting/periods/{period_id}/reopen" in paths
    assert "/api/v1/accounting/periods/{period_id}/lock" in paths
