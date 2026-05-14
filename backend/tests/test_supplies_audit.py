"""Supply lifecycle events surface in the audit log (#24 wildcards)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_supply_created_appears_in_audit_log(
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
        "/api/v1/supplies",
        headers=h,
        json={
            "name": "Isopropyl Alcohol",
            "unit": "ml",
            "unit_cost": "0.01",
            "vendor": "Amazon",
        },
    )
    assert create.status_code == 201, create.text

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "catalog.SupplyCreated"},
    )
    assert audit.status_code == 200, audit.text
    body = audit.json()
    assert body["items"], body
    row = body["items"][0]
    assert row["event_type"] == "catalog.SupplyCreated"
    assert "Isopropyl Alcohol" in row["summary"]
    excerpt = row["payload_excerpt"]
    assert excerpt["name"] == "Isopropyl Alcohol"
    assert excerpt["unit"] == "ml"
    assert excerpt["vendor"] == "Amazon"
