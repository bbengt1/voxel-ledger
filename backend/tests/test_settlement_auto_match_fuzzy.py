"""Auto-match: fuzzy on (channel, amount ± $0.50, occurred_on ± 3 days) (Phase 9.9, #161)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.sales_channel import SalesChannel
from app.services import settlement_matcher as matcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import seed_settlement_stack, seed_user
from tests._settlement_match_helpers import seed_sale, seed_settlement_with_lines


@pytest.mark.asyncio
async def test_fuzzy_match(app_session: AsyncSession) -> None:
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session, email="fuzzy-owner@example.com")
    channel = (
        await app_session.execute(
            select(SalesChannel).where(SalesChannel.id == stack["channel_id"])
        )
    ).scalar_one()
    today = datetime.now(UTC)
    # No external_order_id on the sale → exact match misses; fuzzy
    # matches on channel + amount + created_at.
    sale = await seed_sale(
        app_session,
        channel_id=channel.id,
        actor_user_id=user.id,
        external_order_id=None,
        total_amount="50.00",
        occurred_at=today,
    )

    settlement, lines = await seed_settlement_with_lines(
        app_session,
        channel=channel,
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
        lines=[
            # 1¢ different and a day later — well within tolerance.
            {
                "line_kind": "sale",
                "amount": "50.01",
                "occurred_on": today.date(),
            }
        ],
    )

    results = await matcher.run_match(
        session=app_session, settlement_id=settlement.id, actor_user_id=user.id
    )
    matched = [r for r in results if r.matched]
    assert len(matched) == 1
    assert matched[0].matched_sale_id == sale.id
    assert matched[0].strategy == "fuzzy_amount_date"
