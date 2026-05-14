"""After creating a material, the audit log surfaces the event with the
correct summary and whitelisted excerpt fields."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_material_created_appears_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    # Owner seeded via the same helper used by Phase 1.6 tests.
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
        "/api/v1/materials",
        headers=h,
        json={
            "name": "Standard PLA",
            "brand": "Polymaker",
            "material_type": "PLA",
            "color": "black",
        },
    )
    assert create.status_code == 201, create.text

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "catalog.MaterialCreated"},
    )
    assert audit.status_code == 200, audit.text
    body = audit.json()
    assert body["items"], body
    row = body["items"][0]
    assert row["event_type"] == "catalog.MaterialCreated"
    assert "Standard PLA" in row["summary"]
    assert row["payload_excerpt"]["name"] == "Standard PLA"
    assert row["payload_excerpt"]["brand"] == "Polymaker"
    assert row["payload_excerpt"]["material_type"] == "PLA"
    assert row["payload_excerpt"]["color"] == "black"


@pytest.mark.asyncio
async def test_material_received_excerpt_omits_notes(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """``notes`` is intentionally NOT whitelisted: free-text might
    contain sensitive vendor / payment data. Verify the excerpt only
    surfaces the agreed-upon fields."""
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

    # Phase 3.2: receipts need a fallback receiving location.
    await client.post(
        "/api/v1/inventory/locations",
        headers=h,
        json={"name": "Receiving", "code": "RX", "kind": "workshop"},
    )
    create = await client.post(
        "/api/v1/materials",
        headers=h,
        json={"name": "PLA", "material_type": "PLA"},
    )
    mid = create.json()["id"]

    r = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=h,
        json={
            "grams": "1000",
            "total_cost": "20.00",
            "vendor": "ACME",
            "notes": "credit card ending 1234",
        },
    )
    assert r.status_code == 201, r.text

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "inventory.MaterialReceived"},
    )
    body = audit.json()
    assert body["items"], body
    excerpt = body["items"][0]["payload_excerpt"]
    assert set(excerpt.keys()) == {"material_id", "grams", "total_cost"}
    assert "notes" not in excerpt
    assert "credit card" not in str(body)
