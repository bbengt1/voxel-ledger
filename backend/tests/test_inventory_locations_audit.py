"""Inventory location lifecycle events surface in the audit log."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_location_created_appears_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
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
    token = login.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v1/inventory/locations",
        headers=h,
        json={"name": "Workshop bench", "code": "WSB", "kind": "workshop"},
    )
    assert create.status_code == 201, create.text

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "inventory.LocationCreated"},
    )
    assert audit.status_code == 200, audit.text
    body = audit.json()
    assert body["items"], body
    row = body["items"][0]
    assert row["event_type"] == "inventory.LocationCreated"
    assert "WSB" in row["summary"]
    excerpt = row["payload_excerpt"]
    assert excerpt["name"] == "Workshop bench"
    assert excerpt["code"] == "WSB"
    assert excerpt["kind"] == "workshop"


@pytest.mark.asyncio
async def test_location_updated_and_archived_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
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
    token = login.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v1/inventory/locations",
        headers=h,
        json={"name": "Workshop bench", "code": "WSB", "kind": "workshop"},
    )
    lid = create.json()["id"]
    await client.patch(
        f"/api/v1/inventory/locations/{lid}",
        headers=h,
        json={"name": "Workshop bench (main)"},
    )
    await client.post(f"/api/v1/inventory/locations/{lid}/archive", headers=h)

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "inventory.LocationUpdated"},
    )
    items = audit.json()["items"]
    assert items
    excerpt = items[0]["payload_excerpt"]
    assert "before" in excerpt
    assert "after" in excerpt
    assert excerpt["after"]["name"] == "Workshop bench (main)"

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "inventory.LocationArchived"},
    )
    assert audit.json()["items"]
