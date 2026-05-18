"""Auto-match: ``ignore`` action flips state without posting JE
(Phase 8.10, #137)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.bank import BankTransactionState
from app.services import bank_auto_matcher, bank_match_rules
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    seed_bank_account,
    seed_bank_transaction,
    seed_open_period,
    seed_user,
)


@pytest.mark.asyncio
async def test_ignore_action(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)

    await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="INTERNAL TRANSFER",
        action_kind="ignore",
        actor_user_id=user.id,
    )
    await app_session.commit()

    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="INTERNAL TRANSFER FROM SAVINGS",
        amount=Decimal("100.00"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()
    assert len(results) == 1
    assert results[0].action_kind == "ignore"
    assert results[0].journal_entry_id is None

    await app_session.refresh(tx)
    assert tx.state == BankTransactionState.IGNORED
    assert tx.matched_journal_line_id is None
