"""Auth endpoints emit the right events with the right payloads."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.models.event import Event
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed(session: AsyncSession) -> None:
    await create_user(
        session,
        email="owner@example.com",
        password="hunter2-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_login_success_emits_login_succeeded(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed(app_session)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "hunter2-correct"},
    )
    assert r.status_code == 200
    events = list((await app_session.execute(select(Event).order_by(Event.position))).scalars())
    types = [e.type for e in events]
    assert "auth.LoginSucceeded" in types
    succeeded = next(e for e in events if e.type == "auth.LoginSucceeded")
    assert succeeded.payload["email"] == "owner@example.com"
    assert succeeded.actor_user_id is not None


@pytest.mark.asyncio
async def test_login_failed_emits_login_failed(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed(app_session)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "WRONG"},
    )
    assert r.status_code == 401
    events = list((await app_session.execute(select(Event).order_by(Event.position))).scalars())
    types = [e.type for e in events]
    assert "auth.LoginFailed" in types
    failed = next(e for e in events if e.type == "auth.LoginFailed")
    assert failed.payload["email"] == "owner@example.com"
    assert failed.payload["reason"] == "bad_password"
    # Crucially: no password / hash leaked anywhere in the payload.
    assert "password" not in failed.payload
    assert "password_hash" not in failed.payload


@pytest.mark.asyncio
async def test_login_inactive_emits_login_inactive(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await create_user(
        app_session,
        email="zombie@example.com",
        password="hunter2-correct",
        full_name="Zombie",
        role=Role.OWNER,
        bcrypt_rounds=4,
        is_active=False,
    )
    await app_session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "zombie@example.com", "password": "hunter2-correct"},
    )
    assert r.status_code == 401
    events = list((await app_session.execute(select(Event))).scalars())
    types = [e.type for e in events]
    assert "auth.LoginInactive" in types


@pytest.mark.asyncio
async def test_logout_emits_logged_out(client: AsyncClient, app_session: AsyncSession) -> None:
    await _seed(app_session)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "hunter2-correct"},
    )
    refresh = login.json()["refresh_token"]
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh})
    assert r.status_code == 204
    events = list((await app_session.execute(select(Event))).scalars())
    types = [e.type for e in events]
    assert "auth.LoggedOut" in types


@pytest.mark.asyncio
async def test_refresh_emits_refresh_rotated(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed(app_session)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "hunter2-correct"},
    )
    refresh = login.json()["refresh_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    events = list((await app_session.execute(select(Event))).scalars())
    types = [e.type for e in events]
    assert "auth.RefreshRotated" in types
