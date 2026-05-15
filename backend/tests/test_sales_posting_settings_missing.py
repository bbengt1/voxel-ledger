"""Missing sales-posting defaults raise a clear error (Phase 6.3, #95)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as inventory_tx_service
from app.services import products as products_service
from app.services import sales as sales_service
from app.services.cogs.service import MissingSalesPostingAccountError
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user


@pytest.mark.asyncio
async def test_confirm_raises_when_cogs_account_unset(
    app_session: AsyncSession,
) -> None:
    """No ``sales_posting.*`` settings configured → clear error.

    The error message must contain ``"configure default sales-posting accounts"``
    so the router's 400 response is unambiguous for operators.
    """
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="C",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=[
            {
                "kind": "manual",
                "description": "Line",
                "quantity": "1",
                "unit_price": "10.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    with pytest.raises(MissingSalesPostingAccountError) as exc_info:
        await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    assert "configure default sales-posting accounts" in str(exc_info.value)


@pytest.mark.asyncio
async def test_confirm_raises_when_inventory_account_unset(
    app_session: AsyncSession,
) -> None:
    """Drop only ``default_inventory_account_id`` → clear error.

    Verifies the inventory credit is routed by a dedicated setting, not
    by walking up the chart-of-accounts from the COGS account's parent.
    """
    from app.models.inventory_transaction import KIND_PRODUCTION_IN

    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )

    # Clear ONLY the inventory-account setting; leave the other three
    # configured. This proves the inventory credit no longer falls back
    # to walking the COGS account's parent.
    await SettingsService.set(
        "sales_posting.default_inventory_account_id",
        None,
        session=app_session,
        actor_user_id=user.id,
    )
    await app_session.commit()

    location = await locations_service.create(
        app_session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )
    product = await products_service.create(
        app_session,
        name="Widget",
        description=None,
        unit_price=Decimal("20.00"),
        sku=f"PRD-{uuid.uuid4().hex[:6]}",
        actor_user_id=None,
    )
    await app_session.commit()
    await inventory_tx_service.record(
        app_session,
        kind=KIND_PRODUCTION_IN,
        entity_kind="product",
        entity_id=product.id,
        location_id=location.id,
        quantity=Decimal("5"),
        unit_cost=Decimal("2.00"),
        actor_user_id=None,
    )
    await app_session.commit()

    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="C",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=[
            {
                "kind": "product",
                "product_id": str(product.id),
                "description": "Widget",
                "quantity": "1",
                "unit_price": "20.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    with pytest.raises(MissingSalesPostingAccountError) as exc_info:
        await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    assert "configure default sales-posting accounts" in str(exc_info.value)
    assert "default_inventory_account_id" in str(exc_info.value)
