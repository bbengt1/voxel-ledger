"""Auto-match: posted JE structure verification — bank side is correct
for both signs of ``tx.amount`` (Phase 8.10, #137)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services import bank_auto_matcher, bank_match_rules
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    seed_bank_account,
    seed_bank_transaction,
    seed_expense_account,
    seed_income_account,
    seed_open_period,
    seed_user,
)


async def _fetch_lines(session: AsyncSession, entry_id) -> list[JournalLine]:
    return list(
        (
            await session.execute(
                select(JournalLine)
                .where(JournalLine.entry_id == entry_id)
                .order_by(JournalLine.line_number)
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.asyncio
async def test_outflow_credits_bank(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)

    await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="RENT",
        action_kind="post_to_account",
        debit_account_id=expense.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    await app_session.commit()
    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="RENT MAY",
        amount=Decimal("-1200.00"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()
    assert results[0].journal_entry_id is not None
    entry = (
        await app_session.execute(
            select(JournalEntry).where(JournalEntry.id == results[0].journal_entry_id)
        )
    ).scalar_one()
    lines = await _fetch_lines(app_session, entry.id)
    bank_line = next(line for line in lines if line.account_id == bank.id)
    other_line = next(line for line in lines if line.account_id == expense.id)
    assert bank_line.credit == Decimal("1200.000000")
    assert bank_line.debit == Decimal("0.000000")
    assert other_line.debit == Decimal("1200.000000")
    assert other_line.credit == Decimal("0.000000")
    _ = tx


@pytest.mark.asyncio
async def test_inflow_debits_bank(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    income = await seed_income_account(app_session)

    await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="DEPOSIT",
        action_kind="post_to_account",
        debit_account_id=bank.id,
        credit_account_id=income.id,
        actor_user_id=user.id,
    )
    await app_session.commit()
    await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="DEPOSIT PAYROLL",
        amount=Decimal("2500.00"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()
    entry_id = results[0].journal_entry_id
    assert entry_id is not None
    lines = await _fetch_lines(app_session, entry_id)
    bank_line = next(line for line in lines if line.account_id == bank.id)
    other_line = next(line for line in lines if line.account_id == income.id)
    assert bank_line.debit == Decimal("2500.000000")
    assert bank_line.credit == Decimal("0.000000")
    assert other_line.credit == Decimal("2500.000000")
    assert other_line.debit == Decimal("0.000000")
