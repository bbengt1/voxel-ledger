"""Settlement totals: gross - fees - refunds + adjustments == payout (Phase 9.8, #160)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from app.services import settlement_imports as service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import sample_etsy_csv_bytes, seed_settlement_stack, seed_user


@pytest.mark.asyncio
async def test_totals_balance_within_one_cent(client, app_session: AsyncSession) -> None:
    _ = client  # ensures schema exists on app engine
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session)

    settlement = await service.import_file(
        session=app_session,
        channel_id=stack["channel_id"],
        file_bytes=sample_etsy_csv_bytes(),
        filename="etsy.csv",
        format_kind="etsy",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
    )
    await app_session.commit()

    # gross=20.00 sale; fee=abs(-1.30)=1.30; refund=abs(-5.00)=5.00;
    # adjustment=0.50; payout=20.00-1.30-5.00+0.50=14.20.
    assert settlement.gross_amount == Decimal("20.00")
    assert settlement.fee_amount == Decimal("1.30")
    assert settlement.refund_amount == Decimal("5.00")
    assert settlement.adjustment_amount == Decimal("0.50")

    diff = (
        settlement.gross_amount
        - settlement.fee_amount
        - settlement.refund_amount
        + settlement.adjustment_amount
        - settlement.payout_amount
    )
    assert abs(diff) <= Decimal("0.01")
