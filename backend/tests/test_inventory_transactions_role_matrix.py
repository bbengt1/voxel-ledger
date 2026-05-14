"""Inventory transactions endpoint role matrix.

POST / require owner+production for every kind except ``sale_out``
(owner+sales). POST /transfer requires owner+production. GET endpoints
are visible to every authenticated role.
"""

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


async def _seed_world(client: AsyncClient, owner_h):
    loc = (
        await client.post(
            "/api/v1/inventory/locations",
            headers=owner_h,
            json={"name": "WS", "code": "WS", "kind": "workshop"},
        )
    ).json()
    mat = (
        await client.post(
            "/api/v1/materials",
            headers=owner_h,
            json={"name": "PLA", "brand": "A", "material_type": "PLA"},
        )
    ).json()
    return loc, mat


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,kind,expected",
    [
        (Role.OWNER, "production_in", 201),
        (Role.PRODUCTION, "production_in", 201),
        (Role.SALES, "production_in", 403),
        (Role.BOOKKEEPER, "production_in", 403),
        (Role.VIEWER, "production_in", 403),
        (Role.OWNER, "sale_out", 201),
        (Role.SALES, "sale_out", 201),
        (Role.PRODUCTION, "sale_out", 403),
        (Role.BOOKKEEPER, "sale_out", 403),
        (Role.VIEWER, "sale_out", 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    kind: str,
    expected: int,
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    loc, mat = await _seed_world(client, _h(owner))

    if role == Role.OWNER:
        token = owner
    else:
        token = await _token_for(role, client, app_session)

    r = await client.post(
        "/api/v1/inventory/transactions",
        headers=_h(token),
        json={
            "kind": kind,
            "entity_kind": "material",
            "entity_id": mat["id"],
            "location_id": loc["id"],
            "quantity": "10",
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.PRODUCTION, Role.SALES, Role.BOOKKEEPER, Role.VIEWER],
)
async def test_list_visible_to_every_authenticated_role(
    client: AsyncClient, app_session: AsyncSession, role: Role
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/inventory/transactions", headers=_h(token))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_unauthenticated_endpoints_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/inventory/transactions")
    assert r.status_code == 401
    r = await client.post("/api/v1/inventory/transactions", json={})
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
async def test_transfer_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    loc_a = (
        await client.post(
            "/api/v1/inventory/locations",
            headers=_h(owner),
            json={"name": "A", "code": "A", "kind": "workshop"},
        )
    ).json()
    loc_b = (
        await client.post(
            "/api/v1/inventory/locations",
            headers=_h(owner),
            json={"name": "B", "code": "B", "kind": "staging"},
        )
    ).json()
    mat = (
        await client.post(
            "/api/v1/materials",
            headers=_h(owner),
            json={"name": "PLA", "brand": "A", "material_type": "PLA"},
        )
    ).json()

    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/inventory/transactions/transfer",
        headers=_h(token),
        json={
            "entity_kind": "material",
            "entity_id": mat["id"],
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
            "quantity": "10",
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/inventory/transactions" in paths
    assert "/api/v1/inventory/transactions/transfer" in paths
    assert "/api/v1/inventory/transactions/{transaction_id}" in paths
