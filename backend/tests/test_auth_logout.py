"""Logout revokes the entire family."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_logout_revokes_family(client: AsyncClient, app_session: AsyncSession) -> None:
    await create_user(
        app_session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    refresh1 = login.json()["refresh_token"]

    # Rotate once to extend the family.
    rot = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    refresh2 = rot.json()["refresh_token"]

    out = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh2})
    assert out.status_code == 204

    # Both tokens are now dead.
    for tok in (refresh1, refresh2):
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tok})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_unknown_token_is_204(client: AsyncClient) -> None:
    # Don't leak whether a token existed.
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "ghost"})
    assert resp.status_code == 204
