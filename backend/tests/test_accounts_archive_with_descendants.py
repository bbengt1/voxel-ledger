"""Archiving an account with active descendants is blocked (Phase 4.1)."""

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
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_archive_blocked_with_active_descendants(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    parent = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    pid = parent.json()["id"]
    await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1010", "name": "Cash", "type": "asset", "parent_account_id": pid},
    )
    r = await client.post(f"/api/v1/accounts/{pid}/archive", headers=_h(token))
    assert r.status_code == 400
    assert "descendant" in r.text.lower()


@pytest.mark.asyncio
async def test_archive_allowed_when_descendants_archived(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    parent = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    pid = parent.json()["id"]
    child = await client.post(
        "/api/v1/accounts",
        headers=_h(token),
        json={"code": "1010", "name": "Cash", "type": "asset", "parent_account_id": pid},
    )
    cid = child.json()["id"]

    # Archive the child first.
    arch_child = await client.post(f"/api/v1/accounts/{cid}/archive", headers=_h(token))
    assert arch_child.status_code == 200
    # Now the parent can be archived.
    arch_parent = await client.post(f"/api/v1/accounts/{pid}/archive", headers=_h(token))
    assert arch_parent.status_code == 200
    assert arch_parent.json()["is_archived"] is True
