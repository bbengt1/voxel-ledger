"""kind=marketplace_initiated bypasses approval gating (Phase 6.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.refund import RefundState
from app.services import refunds as refunds_service
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession

from tests._refunds_helpers import create_confirmed_sale, seed_product_with_stock
from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user


@pytest.mark.asyncio
async def test_marketplace_initiated_skips_gate_even_over_threshold(
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
    # Trivial threshold — any refund would normally pend.
    await SettingsService.set(
        "sales.refund.approval_threshold",
        Decimal("1.00"),
        session=app_session,
        actor_user_id=user.id,
    )
    await app_session.commit()

    product, _ = await seed_product_with_stock(app_session, qty="20", unit_cost="5")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="5",
        unit_price="50.00",
    )
    sale_item = sale.items[0]
    result = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="marketplace_initiated",
        reason_code="dispute",
        notes=None,
        restock_inventory=True,
        items=[
            {
                "sale_item_id": str(sale_item.id),
                "quantity": "5",
                "unit_amount": "50.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.approval_request_id is None
    assert result.refund.state == RefundState.APPROVED
    assert result.refund.total_amount == Decimal("250.000000")
