"""Refresh-token rotation and family revocation."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, session: AsyncSession) -> tuple[str, str]:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    assert resp.status_code == 200
    body = resp.json()
    return body["access_token"], body["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_happy_path(client: AsyncClient, app_session: AsyncSession) -> None:
    _, refresh1 = await _login(client, app_session)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["refresh_token"] != refresh1
    assert body["access_token"]


@pytest.mark.asyncio
async def test_reused_refresh_token_burns_family(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Chain N rotations, replay any earlier token, all subsequent 401."""
    _, current = await _login(client, app_session)
    history = [current]
    for _ in range(5):
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": history[-1]})
        assert resp.status_code == 200
        history.append(resp.json()["refresh_token"])

    # Replay an old (already-rotated, so revoked) token.
    replay = history[2]
    bad = await client.post("/api/v1/auth/refresh", json={"refresh_token": replay})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "refresh token reused"

    # After family revocation, even the most-recently-issued token fails.
    latest = history[-1]
    follow = await client.post("/api/v1/auth/refresh", json={"refresh_token": latest})
    assert follow.status_code == 401

    # And every other token in the family is also burned.
    for tok in history:
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": tok})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_unknown_refresh_token_401(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "nope"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid refresh token"
