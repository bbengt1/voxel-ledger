"""Account lifecycle events surface in the audit log (Phase 4.1)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _setup(client: AsyncClient, session: AsyncSession) -> dict[str, str]:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_account_created_in_audit_log(client: AsyncClient, app_session: AsyncSession) -> None:
    h = await _setup(client, app_session)
    create = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    assert create.status_code == 201
    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "accounting.AccountCreated"},
    )
    body = audit.json()
    assert body["items"]
    row = body["items"][0]
    assert row["event_type"] == "accounting.AccountCreated"
    assert "1000" in row["summary"]
    excerpt = row["payload_excerpt"]
    assert excerpt["code"] == "1000"
    assert excerpt["name"] == "Assets"
    assert excerpt["type"] == "asset"
    assert "parent_account_id" in excerpt


@pytest.mark.asyncio
async def test_account_updated_and_archived_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    h = await _setup(client, app_session)
    create = await client.post(
        "/api/v1/accounts",
        headers=h,
        json={"code": "1000", "name": "Assets", "type": "asset"},
    )
    aid = create.json()["id"]
    await client.patch(
        f"/api/v1/accounts/{aid}",
        headers=h,
        json={"name": "Total Assets"},
    )
    await client.post(f"/api/v1/accounts/{aid}/archive", headers=h)

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "accounting.AccountUpdated"},
    )
    items = audit.json()["items"]
    assert items
    excerpt = items[0]["payload_excerpt"]
    assert "before" in excerpt
    assert "after" in excerpt
    assert excerpt["after"]["name"] == "Total Assets"

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "accounting.AccountArchived"},
    )
    assert audit.json()["items"]
