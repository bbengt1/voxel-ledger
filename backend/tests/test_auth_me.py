"""/auth/me — token presence + freshness + role surfaced."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.security import create_access_token
from app.core.settings import Settings
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_me_no_token_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_fresh_token_200(client: AsyncClient, app_session: AsyncSession) -> None:
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
    access = login.json()["access_token"]
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "owner@example.com"
    assert body["role"] == "owner"

    # Confirm JWT contents directly.
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
        bcrypt_rounds=4,
    )
    decoded = jwt.decode(
        access,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert decoded["role"] == "owner"
    assert decoded["sub"] == body["id"]


@pytest.mark.asyncio
async def test_me_expired_token_401(
    client: AsyncClient, app_session: AsyncSession, settings: Settings
) -> None:
    from app.services.auth import get_user_by_email

    await create_user(
        app_session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    user = await get_user_by_email(app_session, "owner@example.com")
    assert user is not None

    expired = create_access_token(
        settings=settings,
        user_id=user.id,
        role=user.role.value,
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert r.json()["detail"] == "token expired"


@pytest.mark.asyncio
async def test_me_bad_token_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
