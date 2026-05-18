"""Auto-match: regex rule (Phase 8.10, #137)."""

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
async def test_regex_match_fires(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)

    await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="regex",
        match_field="description",
        match_value=r"^STARBUCKS|^DUNKIN",
        action_kind="post_to_account",
        debit_account_id=expense.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    await app_session.commit()

    tx_match = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="STARBUCKS #1234 SEATTLE",
        amount=Decimal("-7.25"),
    )
    tx_miss = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="GROCERY MART",
        amount=Decimal("-32.10"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()

    assert len(results) == 1
    await app_session.refresh(tx_match)
    await app_session.refresh(tx_miss)
    assert tx_match.state == BankTransactionState.MATCHED
    assert tx_miss.state == BankTransactionState.UNMATCHED
