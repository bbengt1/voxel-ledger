"""Full + partial refund quantity validation (Phase 6.5, #97)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.refund import RefundState
from app.services import refunds as refunds_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._refunds_helpers import create_confirmed_sale, seed_product_with_stock
from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user


@pytest.mark.asyncio
async def test_full_refund_of_sale_line(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _ = await seed_product_with_stock(app_session, qty="20", unit_cost="5")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="3",
        unit_price="10.00",
    )
    sale_item = sale.items[0]
    result = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="full",
        reason_code="damaged",
        notes=None,
        restock_inventory=True,
        items=[
            {
                "sale_item_id": str(sale_item.id),
                "quantity": "3",
                "unit_amount": "10.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.refund.state == RefundState.APPROVED
    assert result.refund.total_amount == Decimal("30.000000")


@pytest.mark.asyncio
async def test_partial_refund_then_overrefund_is_409(
    app_session: AsyncSession,
) -> None:
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _ = await seed_product_with_stock(app_session, qty="20", unit_cost="5")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="5",
        unit_price="10.00",
    )
    sale_item = sale.items[0]

    # Refund 3 of 5.
    first = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="partial",
        reason_code="damaged",
        notes=None,
        restock_inventory=True,
        items=[
            {
                "sale_item_id": str(sale_item.id),
                "quantity": "3",
                "unit_amount": "10.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert first.refund.state == RefundState.APPROVED

    # Refund another 2 — exactly remaining, OK.
    second = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="partial",
        reason_code="damaged",
        notes=None,
        restock_inventory=True,
        items=[
            {
                "sale_item_id": str(sale_item.id),
                "quantity": "2",
                "unit_amount": "10.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert second.refund.state == RefundState.APPROVED

    # Refund 1 more — over-refund.
    with pytest.raises(refunds_service.OverRefundError):
        await refunds_service.create(
            session=app_session,
            sale_id=sale.id,
            kind="partial",
            reason_code="damaged",
            notes=None,
            restock_inventory=True,
            items=[
                {
                    "sale_item_id": str(sale_item.id),
                    "quantity": "1",
                    "unit_amount": "10.00",
                }
            ],
            actor_user_id=user.id,
        )


@pytest.mark.asyncio
async def test_overrefund_endpoint_409(client, app_session: AsyncSession) -> None:
    from app.models.auth import Role

    from tests._sales_helpers import auth_header, token_for

    user = await seed_user(app_session, email="seed-owner@example.com")
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _ = await seed_product_with_stock(app_session, qty="20", unit_cost="5")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="2",
        unit_price="10.00",
    )
    sale_item = sale.items[0]

    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/refunds",
        headers=auth_header(token),
        json={
            "sale_id": str(sale.id),
            "kind": "partial",
            "reason_code": "damaged",
            "restock_inventory": True,
            "items": [
                {
                    "sale_item_id": str(sale_item.id),
                    "quantity": "5",
                    "unit_amount": "10.00",
                }
            ],
        },
    )
    assert r.status_code == 409, r.text
