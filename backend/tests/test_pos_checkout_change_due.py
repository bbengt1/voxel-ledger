"""POS checkout returns change_due = tendered - total (Phase 6.4, #96)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pos_helpers import seed_pos_channel, seed_product_with_inventory
from tests._sales_helpers import auth_header, seed_posting_defaults, token_for


async def _seed_cart_for_checkout(
    client: AsyncClient, app_session: AsyncSession, barcode: str, unit_price: str
) -> tuple[str, str]:
    posting = await seed_posting_defaults(app_session)
    channel = await seed_pos_channel(
        app_session, default_revenue_account_id=posting["revenue_account_id"]
    )
    await seed_product_with_inventory(app_session, barcode=barcode, unit_price=unit_price)
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
        json={"barcode": barcode},
    )
    return cart_id, owner


@pytest.mark.asyncio
async def test_change_due_overpayment(
    client: AsyncClient, app_session: AsyncSession, accounting_period_today
) -> None:
    cart_id, owner = await _seed_cart_for_checkout(
        client, app_session, barcode="CHG1", unit_price="7.50"
    )
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/checkout",
        headers=auth_header(owner),
        json={"payment_method": "cash", "tendered_amount": "10.00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["change_due"] == "2.500000"


@pytest.mark.asyncio
async def test_change_due_exact_payment(
    client: AsyncClient, app_session: AsyncSession, accounting_period_today
) -> None:
    cart_id, owner = await _seed_cart_for_checkout(
        client, app_session, barcode="CHG2", unit_price="12.34"
    )
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/checkout",
        headers=auth_header(owner),
        json={"payment_method": "cash", "tendered_amount": "12.34"},
    )
    assert r.status_code == 200, r.text
    from decimal import Decimal

    assert Decimal(r.json()["change_due"]) == Decimal("0")


@pytest.mark.asyncio
async def test_change_due_underpayment_rejected(
    client: AsyncClient, app_session: AsyncSession, accounting_period_today
) -> None:
    cart_id, owner = await _seed_cart_for_checkout(
        client, app_session, barcode="CHG3", unit_price="20.00"
    )
    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/checkout",
        headers=auth_header(owner),
        json={"payment_method": "cash", "tendered_amount": "10.00"},
    )
    assert r.status_code == 400
