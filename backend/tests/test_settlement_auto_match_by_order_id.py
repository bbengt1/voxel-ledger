"""Auto-match: sale line with ``external_order_id`` ties to the in-app sale (Phase 9.9, #161)."""

from __future__ import annotations

import pytest
from app.models.depreciation_schedule import DepreciationEntryState  # noqa: F401  (re-export check)
from app.models.sales_channel import SalesChannel
from app.models.settlement import SettlementLineState
from app.services import settlement_matcher as matcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import seed_settlement_stack, seed_user
from tests._settlement_match_helpers import (
    seed_sale,
    seed_settlement_with_lines,
)


@pytest.mark.asyncio
async def test_external_order_id_match(app_session: AsyncSession) -> None:
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session, email="match-owner@example.com")
    channel = (
        await app_session.execute(
            select(SalesChannel).where(SalesChannel.id == stack["channel_id"])
        )
    ).scalar_one()
    sale = await seed_sale(
        app_session,
        channel_id=channel.id,
        actor_user_id=user.id,
        external_order_id="ETSY-1001",
        total_amount="20.00",
    )

    settlement, lines = await seed_settlement_with_lines(
        app_session,
        channel=channel,
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
        lines=[
            {"line_kind": "sale", "amount": "20.00", "external_order_id": "ETSY-1001"},
            {"line_kind": "fee", "amount": "-1.30"},
        ],
    )

    results = await matcher.run_match(
        session=app_session, settlement_id=settlement.id, actor_user_id=user.id
    )
    assert any(
        r.matched and r.matched_sale_id == sale.id and r.strategy == "external_order_id"
        for r in results
    )

    sale_line = next(line for line in lines if line.line_kind.value == "sale")
    await app_session.refresh(sale_line)
    assert sale_line.matched_sale_id == sale.id
    assert sale_line.state == SettlementLineState.MATCHED
