"""Admin endpoint: GET /api/v1/admin/reference-sequences.

Covers role gating (owner-only across the role matrix), response shape,
ordering, and OpenAPI registration so the frontend codegen picks it up.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from app.services.reference_number import ReferenceNumberService
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


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/admin/reference-sequences")
    assert r.status_code == 401


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
async def test_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected: int,
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get(
        "/api/v1/admin/reference-sequences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_response_shape_and_ordering(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)

    # Seed a few sequences across prefixes and years.
    await ReferenceNumberService.allocate("S", session=app_session, year=2026)
    await ReferenceNumberService.allocate("S", session=app_session, year=2026)
    await ReferenceNumberService.allocate("S", session=app_session, year=2027)
    await ReferenceNumberService.allocate("INV", session=app_session, year=2026)
    await app_session.commit()

    r = await client.get(
        "/api/v1/admin/reference-sequences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == [
        {"prefix": "INV", "year": 2026, "last_value": 1},
        {"prefix": "S", "year": 2026, "last_value": 2},
        {"prefix": "S", "year": 2027, "last_value": 1},
    ]


@pytest.mark.asyncio
async def test_empty_list_when_no_allocations(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/admin/reference-sequences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_endpoint_appears_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/admin/reference-sequences" in paths
