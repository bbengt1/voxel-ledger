"""Variance read model: budget vs. actual per slot (Phase 4.5).

Sign convention (see ``app.services.budgets`` module docstring):

* asset / expense: actual = sum(debit) - sum(credit) (debit-natural)
* liability / equity / revenue: actual = sum(credit) - sum(debit)
  (credit-natural)

variance = actual - budget. Under-realized revenue → negative.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.accounting_period import AccountingPeriod
from app.models.division import Division
from app.services import journal_entries as je
from app.services.budgets import BudgetsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, now_utc, seed_account, seed_owner


@pytest.mark.asyncio
async def test_revenue_variance_with_division_filter(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")
    period = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one()

    division = Division(name="Production", code="PROD", is_archived=False)
    session.add(division)
    await session.flush()

    # Budget: Revenue / Production / period = $1000.
    await BudgetsService.set(
        revenue.id,
        division.id,
        period.id,
        Decimal("1000.00"),
        session=session,
        actor_user_id=owner.id,
    )

    # Post $800 of revenue tagged to that division.
    await je.post(
        je.JournalEntryInput(
            description="prod sale",
            posted_at=now_utc(),
            lines=[
                je.JournalLineInput(
                    account_id=cash.id,
                    debit=d("800"),
                    credit=d("0"),
                    line_number=1,
                    division_id=division.id,
                ),
                je.JournalLineInput(
                    account_id=revenue.id,
                    debit=d("0"),
                    credit=d("800"),
                    line_number=2,
                    division_id=division.id,
                ),
            ],
        ),
        session=session,
        actor_user_id=owner.id,
    )

    rows = await BudgetsService.variance(period.id, session=session)
    assert len(rows) == 1
    r = rows[0]
    assert r.account_id == revenue.id
    assert r.division_id == division.id
    assert r.budget_amount == Decimal("1000.000000")
    assert r.actual_amount == Decimal("800.000000")
    assert r.variance == Decimal("-200.000000")
    assert r.variance_pct == Decimal("-0.2000")


@pytest.mark.asyncio
async def test_catch_all_budget_aggregates_when_lines_have_no_division(
    session: AsyncSession, engine
) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")
    period = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one()

    # Catch-all budget: division NULL.
    await BudgetsService.set(
        revenue.id,
        None,
        period.id,
        Decimal("500"),
        session=session,
        actor_user_id=owner.id,
    )

    await je.post(
        je.JournalEntryInput(
            description="untagged sale",
            posted_at=now_utc(),
            lines=[
                je.JournalLineInput(
                    account_id=cash.id, debit=d("500"), credit=d("0"), line_number=1
                ),
                je.JournalLineInput(
                    account_id=revenue.id, debit=d("0"), credit=d("500"), line_number=2
                ),
            ],
        ),
        session=session,
        actor_user_id=owner.id,
    )

    rows = await BudgetsService.variance(period.id, session=session)
    assert len(rows) == 1
    r = rows[0]
    assert r.division_id is None
    assert r.budget_amount == Decimal("500.000000")
    assert r.actual_amount == Decimal("500.000000")
    assert r.variance == Decimal("0.000000")
    assert r.variance_pct == Decimal("0.0000")


@pytest.mark.asyncio
async def test_variance_zero_budget_avoids_division_by_zero(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")
    period = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one()

    await BudgetsService.set(
        revenue.id,
        None,
        period.id,
        Decimal("0"),
        session=session,
        actor_user_id=owner.id,
    )
    await je.post(
        je.JournalEntryInput(
            description="surprise",
            posted_at=now_utc(),
            lines=[
                je.JournalLineInput(
                    account_id=cash.id, debit=d("100"), credit=d("0"), line_number=1
                ),
                je.JournalLineInput(
                    account_id=revenue.id, debit=d("0"), credit=d("100"), line_number=2
                ),
            ],
        ),
        session=session,
        actor_user_id=owner.id,
    )
    rows = await BudgetsService.variance(period.id, session=session)
    assert rows[0].variance_pct == Decimal("0.0000")
