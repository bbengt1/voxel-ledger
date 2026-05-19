"""Manual match + unmatch + ignore endpoints (Phase 9.9, #161)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.models.sales_channel import SalesChannel
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import auth_header, seed_settlement_stack, seed_user, token_for
from tests._settlement_match_helpers import seed_sale, seed_settlement_with_lines


@pytest.mark.asyncio
async def test_manual_match_unmatch_ignore(client: AsyncClient, app_session: AsyncSession) -> None:
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session, email="manual-owner@example.com")
    token = await token_for(Role.OWNER, client, app_session)
    channel = (
        await app_session.execute(
            select(SalesChannel).where(SalesChannel.id == stack["channel_id"])
        )
    ).scalar_one()
    sale = await seed_sale(
        app_session,
        channel_id=channel.id,
        actor_user_id=user.id,
        external_order_id=None,
        total_amount="99.99",
    )

    settlement, lines = await seed_settlement_with_lines(
        app_session,
        channel=channel,
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
        lines=[
            # Distinct amount so fuzzy can't pick it up automatically.
            {"line_kind": "sale", "amount": "12.34"},
            {"line_kind": "fee", "amount": "-2.00"},
        ],
    )
    sale_line = next(line for line in lines if line.line_kind.value == "sale")

    # Manual match
    r = await client.post(
        f"/api/v1/settlements/{settlement.id}/lines/{sale_line.id}/match",
        headers=auth_header(token),
        json={"sale_id": str(sale.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "matched"
    assert r.json()["matched_sale_id"] == str(sale.id)

    # Unmatch
    r2 = await client.post(
        f"/api/v1/settlements/{settlement.id}/lines/{sale_line.id}/unmatch",
        headers=auth_header(token),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["state"] == "unmatched"
    assert r2.json()["matched_sale_id"] is None

    # Ignore
    r3 = await client.post(
        f"/api/v1/settlements/{settlement.id}/lines/{sale_line.id}/ignore",
        headers=auth_header(token),
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["state"] == "ignored"
