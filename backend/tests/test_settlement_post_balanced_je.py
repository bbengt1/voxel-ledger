"""Posting a fully-matched settlement enqueues a balanced role-tagged JE on
the QBO sync outbox (Phase 9.9, #161; QBO-sole-ledger since epic #312,
Phase 5e)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.models.sales_channel import SalesChannel
from app.models.settlement import Settlement, SettlementState
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import auth_header, seed_settlement_stack, seed_user, token_for
from tests._settlement_match_helpers import (
    seed_clearing_account,
    seed_fee_account,
    seed_sale,
    seed_settlement_with_lines,
)


@pytest.mark.asyncio
async def test_post_balanced_je(client: AsyncClient, app_session: AsyncSession) -> None:
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session, email="post-owner@example.com")
    token = await token_for(Role.OWNER, client, app_session)
    channel = (
        await app_session.execute(
            select(SalesChannel).where(SalesChannel.id == stack["channel_id"])
        )
    ).scalar_one()
    # Channel accounts must be configured even though the legs are now
    # role-tagged (resolved at outbox drain time).
    await seed_clearing_account(app_session, channel=channel)
    await seed_fee_account(app_session, channel=channel)

    sale = await seed_sale(
        app_session,
        channel_id=channel.id,
        actor_user_id=user.id,
        external_order_id="ETSY-1001",
        total_amount="20.00",
    )

    today = datetime.now(UTC).date()
    settlement, _ = await seed_settlement_with_lines(
        app_session,
        channel=channel,
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
        period_end=today,
        lines=[
            {"line_kind": "sale", "amount": "20.00", "external_order_id": "ETSY-1001"},
            {"line_kind": "fee", "amount": "-1.30"},
            # no refund / adjustment → gross=20, fee=1.30, payout=18.70
        ],
    )

    # Auto-match.
    r1 = await client.post(
        f"/api/v1/settlements/{settlement.id}/match-now",
        headers=auth_header(token),
    )
    assert r1.status_code == 200, r1.text

    # Post.
    r2 = await client.post(
        f"/api/v1/settlements/{settlement.id}/post",
        headers=auth_header(token),
    )
    assert r2.status_code == 200, r2.text
    payload = r2.json()
    assert payload["state"] == "posted"
    # QBO is the sole ledger (epic #312, Phase 5e): no local JE.
    assert payload["posting_journal_entry_id"] is None

    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "settlement", QboSyncOutbox.local_id == settlement.id
            )
        )
    ).scalar_one()
    by_role = {
        ln["role"]: (ln["posting"], Decimal(ln["amount"])) for ln in outbox_row.payload["lines"]
    }
    # Dr payout 18.70, Dr fees 1.30, Cr clearing 20.00
    assert by_role["payout"] == ("debit", Decimal("18.70"))
    assert by_role["marketplace_fee"] == ("debit", Decimal("1.30"))
    assert by_role["marketplace_clearing"] == ("credit", Decimal("20.00"))

    total_d = sum(amt for posting, amt in by_role.values() if posting == "debit")
    total_c = sum(amt for posting, amt in by_role.values() if posting == "credit")
    assert total_d == total_c == Decimal("20.00")

    fresh = (
        await app_session.execute(select(Settlement).where(Settlement.id == settlement.id))
    ).scalar_one()
    await app_session.refresh(fresh, ["state"])
    assert fresh.state == SettlementState.POSTED
    # Sale was referenced just to ensure auto-match wired in.
    assert sale.id is not None
