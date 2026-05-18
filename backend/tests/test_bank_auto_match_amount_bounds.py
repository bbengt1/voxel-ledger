"""Auto-match: amount bound filter is sign-aware (Phase 8.10, #137)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.bank import BankTransactionState
from app.services import bank_auto_matcher, bank_match_rules
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    seed_bank_account,
    seed_bank_transaction,
    seed_expense_account,
    seed_open_period,
    seed_user,
)


@pytest.mark.asyncio
async def test_amount_bounds_filter(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)

    # Rule fires only on outflows between -100 and -10 (signed range).
    await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="COFFEE",
        action_kind="post_to_account",
        debit_account_id=expense.id,
        credit_account_id=bank.id,
        min_amount=Decimal("-100"),
        max_amount=Decimal("-10"),
        actor_user_id=user.id,
    )
    await app_session.commit()

    in_range = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="COFFEE SHOP",
        amount=Decimal("-50.00"),
    )
    out_of_range_small = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="COFFEE SHOP",
        amount=Decimal("-5.00"),
    )
    out_of_range_big = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="COFFEE SHOP CATERING",
        amount=Decimal("-250.00"),
    )

    await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()

    await app_session.refresh(in_range)
    await app_session.refresh(out_of_range_small)
    await app_session.refresh(out_of_range_big)
    assert in_range.state == BankTransactionState.MATCHED
    assert out_of_range_small.state == BankTransactionState.UNMATCHED
    assert out_of_range_big.state == BankTransactionState.UNMATCHED
