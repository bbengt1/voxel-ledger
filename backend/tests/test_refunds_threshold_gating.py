"""Threshold-gating behavior for refunds (Phase 6.5, #97)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.approval_request import ApprovalRequest, ApprovalState
from app.models.refund import RefundState
from app.services import refunds as refunds_service
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._refunds_helpers import create_confirmed_sale, seed_product_with_stock
from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user


@pytest.mark.asyncio
async def test_under_threshold_auto_approves(app_session: AsyncSession) -> None:
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
        quantity="2",
        unit_price="20.00",
    )

    sale_item = sale.items[0]
    result = await refunds_service.create(
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
                "unit_amount": "20.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.approval_request_id is None
    assert result.refund.state == RefundState.APPROVED
    assert result.refund.total_amount == Decimal("20.000000")


@pytest.mark.asyncio
async def test_over_threshold_creates_approval_request(
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
    # Force a low threshold so a $40 refund crosses it.
    await SettingsService.set(
        "sales.refund.approval_threshold",
        Decimal("10.00"),
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
        quantity="2",
        unit_price="20.00",
    )
    sale_item = sale.items[0]
    result = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="full",
        reason_code="dispute",
        notes=None,
        restock_inventory=True,
        items=[
            {
                "sale_item_id": str(sale_item.id),
                "quantity": "2",
                "unit_amount": "20.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.approval_request_id is not None
    assert result.refund.state == RefundState.PENDING_APPROVAL

    approval = (
        await app_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == result.approval_request_id)
        )
    ).scalar_one()
    assert approval.state == ApprovalState.PENDING.value
    assert approval.request_type == "sales.large_refund"
    assert approval.subject_kind == "refund"
    assert approval.subject_id == result.refund.id


@pytest.mark.asyncio
async def test_endpoint_returns_202_on_pending_approval(client, app_session: AsyncSession) -> None:
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
    await SettingsService.set(
        "sales.refund.approval_threshold",
        Decimal("5.00"),
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
        quantity="2",
        unit_price="20.00",
    )
    sale_item = sale.items[0]

    token = await token_for(Role.SALES, client, app_session)
    r = await client.post(
        "/api/v1/refunds",
        headers=auth_header(token),
        json={
            "sale_id": str(sale.id),
            "kind": "full",
            "reason_code": "dispute",
            "restock_inventory": True,
            "items": [
                {
                    "sale_item_id": str(sale_item.id),
                    "quantity": "2",
                    "unit_amount": "20.00",
                }
            ],
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["approval_request_id"] is not None
    assert body["refund"]["state"] == "pending_approval"
