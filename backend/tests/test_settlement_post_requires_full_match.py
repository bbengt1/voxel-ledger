"""``post`` is blocked while any sale/refund line is unmatched (Phase 9.9, #161)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.models.sales_channel import SalesChannel
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import auth_header, seed_settlement_stack, seed_user, token_for
from tests._settlement_match_helpers import (
    seed_clearing_account,
    seed_fee_account,
    seed_settlement_with_lines,
)


@pytest.mark.asyncio
async def test_post_blocked_when_unmatched(client: AsyncClient, app_session: AsyncSession) -> None:
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session, email="block-owner@example.com")
    token = await token_for(Role.OWNER, client, app_session)
    channel = (
        await app_session.execute(
            select(SalesChannel).where(SalesChannel.id == stack["channel_id"])
        )
    ).scalar_one()
    await seed_clearing_account(app_session, channel=channel)
    await seed_fee_account(app_session, channel=channel)

    settlement, _lines = await seed_settlement_with_lines(
        app_session,
        channel=channel,
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
        lines=[
            {"line_kind": "sale", "amount": "20.00", "external_order_id": "X"},
            {"line_kind": "fee", "amount": "-1.30"},
        ],
    )
    resp = await client.post(
        f"/api/v1/settlements/{settlement.id}/post", headers=auth_header(token)
    )
    assert resp.status_code == 409, resp.text
    assert "unmatched" in resp.text.lower()
