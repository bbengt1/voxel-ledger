"""User-admin events flow through the wildcard audit projection and
appear in /api/v1/admin/audit-log with expected summary + excerpt."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner_token(client: AsyncClient, session: AsyncSession) -> str:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="O",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_user_created_appears_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newbie@example.com", "full_name": "N", "role": "sales"},
    )

    r = await client.get(
        "/api/v1/admin/audit-log?event_type=users.UserCreated",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["event_type"] == "users.UserCreated"
    assert "newbie@example.com" in row["summary"]
    assert "sales" in row["summary"]
    # Excerpt has email/full_name/role but no password fields.
    excerpt = row["payload_excerpt"]
    assert excerpt["email"] == "newbie@example.com"
    assert excerpt["role"] == "sales"
    assert excerpt["full_name"] == "N"
    assert "password" not in str(excerpt).lower()


@pytest.mark.asyncio
async def test_password_reset_audit_has_no_password(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "rp@example.com", "full_name": "R", "role": "sales"},
    )
    uid = create.json()["user"]["id"]
    rp = await client.post(
        f"/api/v1/users/{uid}/reset-password",
        headers={"Authorization": f"Bearer {token}"},
    )
    new_pwd = rp.json()["generated_password"]

    r = await client.get(
        "/api/v1/admin/audit-log?event_type=users.PasswordResetByAdmin",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = r.json()["items"]
    assert len(items) == 1
    row = items[0]
    # No excerpt registered for this event type — the audit row should have
    # payload_excerpt=None (deny-by-default).
    assert row["payload_excerpt"] is None
    # And the password itself never appears.
    assert new_pwd not in row["summary"]
