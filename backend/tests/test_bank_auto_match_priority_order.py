"""Auto-match: priority + per-account-vs-global tiebreak (Phase 8.10, #137)."""

from __future__ import annotations

from decimal import Decimal

import pytest
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
async def test_lower_priority_wins(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    a = await seed_expense_account(app_session, code="6100", name="ExpA")
    b = await seed_expense_account(app_session, code="6200", name="ExpB")

    # Two rules both match "PIZZA"; priority=10 should win over priority=100.
    high = await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=100,
        match_kind="contains",
        match_field="description",
        match_value="PIZZA",
        action_kind="post_to_account",
        debit_account_id=b.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    low = await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=10,
        match_kind="contains",
        match_field="description",
        match_value="PIZZA",
        action_kind="post_to_account",
        debit_account_id=a.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    await app_session.commit()

    await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="PIZZA HUT",
        amount=Decimal("-25.00"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()
    assert len(results) == 1
    assert results[0].rule_id == low.id  # lower priority number wins
    assert results[0].rule_id != high.id


@pytest.mark.asyncio
async def test_per_account_wins_over_global_at_same_priority(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    a = await seed_expense_account(app_session, code="6100", name="ExpA")
    b = await seed_expense_account(app_session, code="6200", name="ExpB")

    # Same priority — global rule + per-account rule both match.
    global_rule = await bank_match_rules.create(
        session=app_session,
        account_id=None,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="GAS",
        action_kind="post_to_account",
        debit_account_id=b.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    per_account = await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="GAS",
        action_kind="post_to_account",
        debit_account_id=a.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    await app_session.commit()

    await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="GAS STATION",
        amount=Decimal("-40.00"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()
    assert len(results) == 1
    assert results[0].rule_id == per_account.id
    assert results[0].rule_id != global_rule.id
