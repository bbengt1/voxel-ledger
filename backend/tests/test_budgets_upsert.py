"""BudgetsService.set upserts and emits BudgetSet with old_amount (Phase 4.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.accounting_period import AccountingPeriod
from app.models.event import Event
from app.services.budgets import BudgetsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import ensure_schema, seed_account, seed_owner


@pytest.mark.asyncio
async def test_set_creates_then_updates_emits_old_amount(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")
    # seed_owner already created a default open period covering today.
    period = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one()

    # First call — creates.
    row = await BudgetsService.set(
        revenue.id,
        None,
        period.id,
        Decimal("1000.00"),
        session=session,
        actor_user_id=owner.id,
    )
    assert row.amount == Decimal("1000.000000")

    events = (
        (
            await session.execute(
                select(Event).where(Event.type == "accounting.BudgetSet").order_by(Event.position)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["old_amount"] is None
    assert events[0].payload["new_amount"] == "1000.000000"

    # Second call — updates.
    row2 = await BudgetsService.set(
        revenue.id,
        None,
        period.id,
        Decimal("1500.00"),
        session=session,
        actor_user_id=owner.id,
    )
    assert row2.id == row.id
    assert row2.amount == Decimal("1500.000000")

    events = (
        (
            await session.execute(
                select(Event).where(Event.type == "accounting.BudgetSet").order_by(Event.position)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 2
    assert events[1].payload["old_amount"] == "1000.000000"
    assert events[1].payload["new_amount"] == "1500.000000"
