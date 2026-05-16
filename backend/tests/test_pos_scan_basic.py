"""POS basic scan happy-path (Phase 6.4, #96)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pos_helpers import seed_pos_channel, seed_product_with_inventory
from tests._sales_helpers import auth_header, seed_posting_defaults, token_for


@pytest.mark.asyncio
async def test_open_scan_scan_checkout(
    client: AsyncClient,
    app_session: AsyncSession,
    accounting_period_today,
) -> None:
    posting = await seed_posting_defaults(app_session)
    channel = await seed_pos_channel(
        app_session, default_revenue_account_id=posting["revenue_account_id"]
    )
    product, _ = await seed_product_with_inventory(app_session, barcode="12345", unit_price="10.00")

    owner = await token_for(Role.OWNER, client, app_session)

    # Open
    r = await client.post(
        "/api/v1/pos/carts",
        headers=auth_header(owner),
        json={"channel_id": str(channel.id)},
    )
    assert r.status_code == 201, r.text
    cart = r.json()
    cart_id = cart["id"]
    assert cart["state"] == "open"
    assert cart["items"] == []

    # Scan barcode
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/scan",
        headers=auth_header(owner),
        json={"barcode": "12345"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["line_number"] == 1
    assert body["items"][0]["quantity"] == "1.000000"
    assert body["items"][0]["product_id"] == str(product.id)

    # Scan same barcode again — increments quantity, not a new line
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/scan",
        headers=auth_header(owner),
        json={"barcode": "12345"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == "2.000000"
    # Total = 2 * $10.00
    assert body["total"] == "20.000000"

    # Checkout
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/checkout",
        headers=auth_header(owner),
        json={"payment_method": "cash", "tendered_amount": "25.00"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sale"]["state"] == "confirmed"
    assert body["change_due"] == "5.000000"
    assert body["cart"]["state"] == "checked_out"
    assert body["cart"]["sale_id"] == body["sale"]["id"]


@pytest.mark.asyncio
async def test_scan_on_checked_out_cart_rejected(
    client: AsyncClient,
    app_session: AsyncSession,
    accounting_period_today,
) -> None:
    posting = await seed_posting_defaults(app_session)
    channel = await seed_pos_channel(
        app_session, default_revenue_account_id=posting["revenue_account_id"]
    )
    await seed_product_with_inventory(app_session, barcode="ABC", unit_price="5.00")
    owner = await token_for(Role.OWNER, client, app_session)

    r = await client.post(
        "/api/v1/pos/carts",
        headers=auth_header(owner),
        json={"channel_id": str(channel.id)},
    )
    cart_id = r.json()["id"]
    await client.post(
        f"/api/v1/pos/carts/{cart_id}/scan",
        headers=auth_header(owner),
        json={"barcode": "ABC"},
    )
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/checkout",
        headers=auth_header(owner),
        json={"payment_method": "cash", "tendered_amount": "5.00"},
    )
    assert r.status_code == 200, r.text

    # Scan again on a checked-out cart is rejected
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/scan",
        headers=auth_header(owner),
        json={"barcode": "ABC"},
    )
    assert r.status_code == 400
