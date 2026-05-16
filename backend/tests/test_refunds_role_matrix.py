"""Role matrix for the refunds endpoints (Phase 6.5, #97)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._refunds_helpers import create_confirmed_sale, seed_product_with_stock
from tests._sales_helpers import (
    auth_header,
    seed_channel,
    seed_posting_defaults,
    seed_user,
    token_for,
)


async def _prep_sale(app_session: AsyncSession):
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
    return sale


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.SALES, 201),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    sale = await _prep_sale(app_session)
    sale_item_id = sale.items[0].id
    token = await token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/refunds",
        headers=auth_header(token),
        json={
            "sale_id": str(sale.id),
            "kind": "partial",
            "reason_code": "damaged",
            "items": [
                {
                    "sale_item_id": str(sale_item_id),
                    "quantity": "1",
                    "unit_amount": "10.00",
                }
            ],
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.SALES, 200),
        (Role.BOOKKEEPER, 200),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_list_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await token_for(role, client, app_session)
    r = await client.get("/api/v1/refunds", headers=auth_header(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_approve_owner_only(client: AsyncClient, app_session: AsyncSession) -> None:
    sale = await _prep_sale(app_session)
    sale_item_id = sale.items[0].id
    # Force every refund into pending_approval.
    await SettingsService.set(
        "sales.refund.approval_threshold",
        Decimal("0.01"),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    sales_token = await token_for(Role.SALES, client, app_session)
    create = await client.post(
        "/api/v1/refunds",
        headers=auth_header(sales_token),
        json={
            "sale_id": str(sale.id),
            "kind": "partial",
            "reason_code": "damaged",
            "items": [
                {
                    "sale_item_id": str(sale_item_id),
                    "quantity": "1",
                    "unit_amount": "10.00",
                }
            ],
        },
    )
    assert create.status_code == 202, create.text
    refund_id = create.json()["refund"]["id"]

    # Sales cannot approve.
    r_sales = await client.post(
        f"/api/v1/refunds/{refund_id}/approve",
        headers=auth_header(sales_token),
    )
    assert r_sales.status_code == 403

    # Owner can approve.
    owner_token = await token_for(Role.OWNER, client, app_session)
    r_owner = await client.post(
        f"/api/v1/refunds/{refund_id}/approve",
        headers=auth_header(owner_token),
    )
    assert r_owner.status_code == 200, r_owner.text
    assert r_owner.json()["state"] == "approved"
