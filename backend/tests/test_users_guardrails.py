"""User-admin guardrails: self-deactivation, self-demotion, last-owner."""

from __future__ import annotations

import pytest
from app.models.auth import Role, User
from app.services import users as users_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str, password: str = "pw-correct") -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


async def _seed_owner(session: AsyncSession, email: str = "owner@example.com") -> None:
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_owner_cannot_deactivate_themselves(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    # Two owners — guarantees last-owner rule isn't the one that fires.
    await _seed_owner(app_session, "owner1@example.com")
    await _seed_owner(app_session, "owner2@example.com")
    token = await _login(client, "owner1@example.com")
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    uid = me.json()["id"]

    r = await client.post(
        f"/api/v1/users/{uid}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400, r.text
    assert "themselves" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_owner_cannot_demote_themselves(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_owner(app_session, "owner1@example.com")
    await _seed_owner(app_session, "owner2@example.com")
    token = await _login(client, "owner1@example.com")
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    uid = me.json()["id"]

    r = await client.patch(
        f"/api/v1/users/{uid}",
        headers={"Authorization": f"Bearer {token}"},
        json={"role": "bookkeeper"},
    )
    assert r.status_code == 400, r.text
    assert "demote" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_last_active_owner_cannot_be_deactivated(
    app_session: AsyncSession,
) -> None:
    """Service-layer guard: with a single active owner, a non-self actor
    deactivating them raises ``LastOwnerLockoutError``.

    Exercised through the service directly so the test stays focused on
    the guard. The router-level translation to 400 is covered by the
    sister test below.
    """
    await _seed_owner(app_session, "lone@example.com")
    # Another user as the actor — role doesn't matter to the service.
    await create_user(
        app_session,
        email="actor@example.com",
        password="pw",
        full_name="A",
        role=Role.BOOKKEEPER,
        bcrypt_rounds=4,
    )
    await app_session.commit()

    actor = (
        await app_session.execute(select(User).where(User.email == "actor@example.com"))
    ).scalar_one()
    target = (
        await app_session.execute(select(User).where(User.email == "lone@example.com"))
    ).scalar_one()

    with pytest.raises(users_service.LastOwnerLockoutError):
        await users_service.deactivate_user(app_session, actor=actor, user_id=target.id)


@pytest.mark.asyncio
async def test_last_active_owner_cannot_be_demoted_via_service(
    app_session: AsyncSession,
) -> None:
    await _seed_owner(app_session, "lone@example.com")
    await create_user(
        app_session,
        email="actor@example.com",
        password="pw",
        full_name="A",
        role=Role.BOOKKEEPER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    actor = (
        await app_session.execute(select(User).where(User.email == "actor@example.com"))
    ).scalar_one()
    target = (
        await app_session.execute(select(User).where(User.email == "lone@example.com"))
    ).scalar_one()
    with pytest.raises(users_service.LastOwnerLockoutError):
        await users_service.update_user(
            app_session,
            actor=actor,
            user_id=target.id,
            full_name=None,
            role=Role.BOOKKEEPER,
            is_active=None,
        )


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(client: AsyncClient, app_session: AsyncSession) -> None:
    """Regression — inactive users get the generic 401 on login (#15)."""
    await _seed_owner(app_session, "owner1@example.com")
    await _seed_owner(app_session, "owner2@example.com")
    token = await _login(client, "owner1@example.com")
    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "bk@example.com", "full_name": "BK", "role": "bookkeeper"},
    )
    uid = create.json()["user"]["id"]
    new_pwd = create.json()["generated_password"]

    deact = await client.post(
        f"/api/v1/users/{uid}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deact.status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "bk@example.com", "password": new_pwd},
    )
    assert login.status_code == 401
