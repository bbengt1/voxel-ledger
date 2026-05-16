"""POS line + cart discount permutations (Phase 6.4, #96)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pos_helpers import seed_pos_channel, seed_product_with_barcode
from tests._sales_helpers import auth_header, token_for


async def _open_cart_with_scan(
    client: AsyncClient, owner: str, channel_id: str, barcode: str
) -> str:
    r = await client.post(
        "/api/v1/pos/carts",
        headers=auth_header(owner),
        json={"channel_id": channel_id},
    )
    cart_id = r.json()["id"]
    await client.post(
        f"/api/v1/pos/carts/{cart_id}/scan",
        headers=auth_header(owner),
        json={"barcode": barcode},
    )
    return cart_id


@pytest.mark.asyncio
async def test_line_discount_percent(client: AsyncClient, app_session: AsyncSession) -> None:
    channel = await seed_pos_channel(app_session)
    await seed_product_with_barcode(app_session, barcode="P10", unit_price="10.00")
    owner = await token_for(Role.OWNER, client, app_session)
    cart_id = await _open_cart_with_scan(client, owner, str(channel.id), "P10")

    r = await client.patch(
        f"/api/v1/pos/carts/{cart_id}/lines/1",
        headers=auth_header(owner),
        json={"discount_kind": "percent", "discount_value": "10"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 1 * $10 - 10% = $9.00
    assert body["items"][0]["extended_amount"] == "9.000000"
    assert body["total"] == "9.000000"


@pytest.mark.asyncio
async def test_line_discount_amount(client: AsyncClient, app_session: AsyncSession) -> None:
    channel = await seed_pos_channel(app_session)
    await seed_product_with_barcode(app_session, barcode="P20", unit_price="20.00")
    owner = await token_for(Role.OWNER, client, app_session)
    cart_id = await _open_cart_with_scan(client, owner, str(channel.id), "P20")

    r = await client.patch(
        f"/api/v1/pos/carts/{cart_id}/lines/1",
        headers=auth_header(owner),
        json={"discount_kind": "amount", "discount_value": "3"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # $20.00 - $3.00 = $17.00
    assert body["items"][0]["extended_amount"] == "17.000000"
    assert body["total"] == "17.000000"


@pytest.mark.asyncio
async def test_combined_line_and_cart_discount(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Line discount applies first, then cart discount on the remainder."""
    from decimal import Decimal

    from app.services import pos as pos_service
    from app.services.auth import create_user

    channel = await seed_pos_channel(app_session)
    await seed_product_with_barcode(app_session, barcode="P50", unit_price="50.00")
    user_row = await create_user(
        app_session,
        email="combined-discount@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()

    cart = await pos_service.open_cart(channel_id=channel.id, cashier=user_row, session=app_session)
    await app_session.commit()
    await pos_service.scan_barcode(cart.id, "P50", session=app_session, actor=user_row)
    await app_session.commit()
    # Line: 10% off $50 = $45
    await pos_service.apply_discount(
        cart.id,
        kind="percent",
        value=Decimal("10"),
        line_number=1,
        session=app_session,
        actor=user_row,
    )
    await app_session.commit()
    # Cart: $5 off $45 = $40
    await pos_service.apply_discount(
        cart.id,
        kind="amount",
        value=Decimal("5"),
        session=app_session,
        actor=user_row,
    )
    await app_session.commit()
    cart = await pos_service.get(app_session, cart.id)
    totals = pos_service.compute_totals(cart)
    assert totals.total == Decimal("40.000000")
