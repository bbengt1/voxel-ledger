"""Force-logout: deactivation + admin password reset both revoke all
refresh-token families, and subsequent refresh attempts return 401."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_owner(session: AsyncSession) -> None:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_deactivate_revokes_all_refresh_families(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_owner(app_session)
    owner_tokens = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "pw-correct"},
        )
    ).json()
    owner_token = owner_tokens["access_token"]

    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "victim@example.com", "full_name": "V", "role": "sales"},
    )
    uid = create.json()["user"]["id"]
    pwd = create.json()["generated_password"]

    # Victim logs in (twice — two distinct refresh families).
    sess1 = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "victim@example.com", "password": pwd},
        )
    ).json()
    sess2 = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "victim@example.com", "password": pwd},
        )
    ).json()

    # Owner deactivates victim.
    deact = await client.post(
        f"/api/v1/users/{uid}/deactivate",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert deact.status_code == 200

    # Both refresh tokens now fail.
    for sess in (sess1, sess2):
        r = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": sess["refresh_token"]},
        )
        assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_reset_password_revokes_all_families(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_owner(app_session)
    owner_token = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": "pw-correct"},
        )
    ).json()["access_token"]

    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "u@example.com", "full_name": "U", "role": "sales"},
    )
    uid = create.json()["user"]["id"]
    pwd = create.json()["generated_password"]

    sess = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "u@example.com", "password": pwd},
        )
    ).json()

    # Owner resets password.
    rp = await client.post(
        f"/api/v1/users/{uid}/reset-password",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert rp.status_code == 200
    new_pwd = rp.json()["generated_password"]
    assert new_pwd != pwd

    # Old refresh token now rejected.
    r = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": sess["refresh_token"]},
    )
    assert r.status_code == 401

    # User can log in with the new password and refresh works again.
    new_sess = (
        await client.post(
            "/api/v1/auth/login",
            json={"email": "u@example.com", "password": new_pwd},
        )
    ).json()
    r2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_sess["refresh_token"]},
    )
    assert r2.status_code == 200
