"""Per-user preferences endpoints (#258)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token(role: Role, email: str, client: AsyncClient, session: AsyncSession) -> str:
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="t",
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/me/preferences/table_columns.products")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_unset_preference_returns_empty(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token(Role.OWNER, "owner@example.com", client, app_session)
    r = await client.get("/api/v1/me/preferences/table_columns.products", headers=_h(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"key": "table_columns.products", "value": {}}


@pytest.mark.asyncio
async def test_put_then_get_roundtrip(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token(Role.PRODUCTION, "prod@example.com", client, app_session)
    put = await client.put(
        "/api/v1/me/preferences/table_columns.products",
        headers=_h(token),
        json={"value": {"visible": ["sku", "name", "unit_price"]}},
    )
    assert put.status_code == 200, put.text
    assert put.json()["value"]["visible"] == ["sku", "name", "unit_price"]

    got = await client.get("/api/v1/me/preferences/table_columns.products", headers=_h(token))
    assert got.json()["value"]["visible"] == ["sku", "name", "unit_price"]

    # Overwrite replaces the value.
    put2 = await client.put(
        "/api/v1/me/preferences/table_columns.products",
        headers=_h(token),
        json={"value": {"visible": ["sku"]}},
    )
    assert put2.json()["value"]["visible"] == ["sku"]


@pytest.mark.asyncio
async def test_preferences_are_per_user(client: AsyncClient, app_session: AsyncSession) -> None:
    a = await _token(Role.OWNER, "a@example.com", client, app_session)
    b = await _token(Role.OWNER, "b@example.com", client, app_session)
    await client.put(
        "/api/v1/me/preferences/table_columns.products",
        headers=_h(a),
        json={"value": {"visible": ["sku"]}},
    )
    # User B sees their own (empty) preference, not A's.
    got_b = await client.get("/api/v1/me/preferences/table_columns.products", headers=_h(b))
    assert got_b.json()["value"] == {}
