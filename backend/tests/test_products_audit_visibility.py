"""Product events surface in the audit log with the agreed summary +
whitelisted excerpt fields. ``description`` is intentionally NOT
whitelisted."""

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


@pytest.mark.asyncio
async def test_product_created_appears_in_audit_log(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    h = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v1/products",
        headers=h,
        json={
            "name": "Visible Widget",
            "unit_price": "9.99",
            "category": "widgets",
            "description": "vendor-account 1234 free-form",
        },
    )
    assert create.status_code == 201, create.text

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "catalog.ProductCreated"},
    )
    assert audit.status_code == 200, audit.text
    body = audit.json()
    assert body["items"], body
    row = body["items"][0]
    assert row["event_type"] == "catalog.ProductCreated"
    assert "Visible Widget" in row["summary"]
    excerpt = row["payload_excerpt"]
    assert excerpt["name"] == "Visible Widget"
    assert excerpt["category"] == "widgets"
    assert excerpt["sku"].startswith("PROD-")
    # description is NOT whitelisted.
    assert "description" not in excerpt
    assert "vendor-account" not in str(body)


@pytest.mark.asyncio
async def test_price_change_audit_carries_old_and_new(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _owner_token(client, app_session)
    h = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v1/products",
        headers=h,
        json={"name": "Pricey", "unit_price": "10.00"},
    )
    pid = create.json()["id"]
    await client.patch(
        f"/api/v1/products/{pid}",
        headers=h,
        json={"unit_price": "15.00"},
    )

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=h,
        params={"event_type": "catalog.ProductPriceChanged"},
    )
    body = audit.json()
    assert body["items"], body
    excerpt = body["items"][0]["payload_excerpt"]
    # Compare numerically — DB-loaded Decimals come back with full
    # Numeric(18, 6) scale, while freshly-parsed Decimals carry the
    # caller's scale.
    from decimal import Decimal

    assert Decimal(excerpt["old_price"]) == Decimal("10")
    assert Decimal(excerpt["new_price"]) == Decimal("15")
