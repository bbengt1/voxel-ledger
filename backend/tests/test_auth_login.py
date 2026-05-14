"""Auth /login endpoint."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed(session: AsyncSession, **kw: object) -> None:
    await create_user(
        session,
        email=kw.get("email", "owner@example.com"),  # type: ignore[arg-type]
        password=kw.get("password", "hunter2-correct"),  # type: ignore[arg-type]
        full_name=kw.get("full_name", "Test Owner"),  # type: ignore[arg-type]
        role=kw.get("role", Role.OWNER),  # type: ignore[arg-type]
        bcrypt_rounds=4,
        is_active=kw.get("is_active", True),  # type: ignore[arg-type]
    )
    await session.commit()


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, app_session: AsyncSession) -> None:
    await _seed(app_session)

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "hunter2-correct"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 900


@pytest.mark.asyncio
async def test_login_wrong_password(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed(app_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_login_unknown_user_same_error(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed(app_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "anything"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_login_inactive_user_same_error(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed(app_session, is_active=False)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "hunter2-correct"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_login_rate_limited(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed(app_session)
    # default limit is 10/min/IP; punch through it.
    for _ in range(10):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "wrong"},
        )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "hunter2-correct"},
    )
    assert resp.status_code == 429
