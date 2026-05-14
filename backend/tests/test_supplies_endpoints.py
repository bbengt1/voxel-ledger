"""Supplies API: role matrix + happy paths."""

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
    r = await client.get("/api/v1/supplies")
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
        "/api/v1/supplies",
        headers=_h(token),
        json={
            "name": f"Resin Cleaner {role.value}",
            "unit": "ml",
            "unit_cost": "0.05",
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
    r = await client.get("/api/v1/supplies", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/supplies",
        headers=_h(owner),
        json={
            "name": "Bubble Wrap",
            "unit": "m",
            "unit_cost": "0.25",
            "vendor": "ULINE",
            "low_stock_threshold": "50",
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    sid = body["id"]
    from decimal import Decimal as _D

    assert _D(body["unit_cost"]) == _D("0.25")
    # Phase 3.3: no on_hand on create — balances are seeded via the
    # inventory-transactions endpoint as adjustments.
    assert _D(body["total_on_hand"]) == _D("0")
    assert body["per_location_on_hand"] == {}
    assert _D(body["low_stock_threshold"]) == _D("50")

    got = await client.get(f"/api/v1/supplies/{sid}", headers=_h(owner))
    assert got.status_code == 200

    patched = await client.patch(
        f"/api/v1/supplies/{sid}",
        headers=_h(owner),
        json={"unit_cost": "0.30"},
    )
    assert patched.status_code == 200
    assert _D(patched.json()["unit_cost"]) == _D("0.30")

    arch = await client.post(f"/api/v1/supplies/{sid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    un = await client.post(f"/api/v1/supplies/{sid}/unarchive", headers=_h(owner))
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
        "/api/v1/supplies",
        headers=_h(owner),
        json={"name": f"Item-{role.value}", "unit": "each", "unit_cost": "1.00"},
    )
    sid = create.json()["id"]

    if role == Role.OWNER:
        token = owner
    else:
        token = await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/supplies/{sid}/archive", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_list_search_and_archived_filter(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    for name in ("Bubble Wrap", "Foam Insert"):
        await client.post(
            "/api/v1/supplies",
            headers=_h(owner),
            json={"name": name, "unit": "each", "unit_cost": "1.00"},
        )
    r = await client.get("/api/v1/supplies?search=bubble", headers=_h(owner))
    assert r.status_code == 200
    assert [s["name"] for s in r.json()["items"]] == ["Bubble Wrap"]

    create = await client.post(
        "/api/v1/supplies",
        headers=_h(owner),
        json={"name": "Ghost", "unit": "each", "unit_cost": "1.00"},
    )
    sid = create.json()["id"]
    await client.post(f"/api/v1/supplies/{sid}/archive", headers=_h(owner))
    r = await client.get("/api/v1/supplies?is_archived=true", headers=_h(owner))
    assert [s["name"] for s in r.json()["items"]] == ["Ghost"]


@pytest.mark.asyncio
async def test_create_duplicate_active_400(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    body = {"name": "Tape", "unit": "m", "unit_cost": "0.10", "vendor": "ULINE"}
    r1 = await client.post("/api/v1/supplies", headers=_h(owner), json=body)
    assert r1.status_code == 201, r1.text
    r2 = await client.post("/api/v1/supplies", headers=_h(owner), json=body)
    assert r2.status_code == 400, r2.text


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/supplies" in paths
    assert "/api/v1/supplies/{supply_id}" in paths
    assert "/api/v1/supplies/{supply_id}/archive" in paths
    assert "/api/v1/supplies/{supply_id}/unarchive" in paths
