"""Journal-entry post() period gating (Phase 4.3, #66)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models import Base
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.services import accounting_periods as periods_service
from app.services import journal_entries as svc
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, seed_account, seed_owner


def _now() -> datetime:
    return datetime.now(UTC)


async def _accounts(session: AsyncSession):
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")
    return cash, revenue


def _lines(cash_id, rev_id):
    return [
        svc.JournalLineInput(account_id=cash_id, debit=d("10"), credit=d("0"), line_number=1),
        svc.JournalLineInput(account_id=rev_id, debit=d("0"), credit=d("10"), line_number=2),
    ]


@pytest.mark.asyncio
async def test_post_into_open_period_populates_period_id(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)  # also seeds an open period for now.
    cash, rev = await _accounts(session)

    entry = await svc.post(
        svc.JournalEntryInput(description="ok", posted_at=_now(), lines=_lines(cash.id, rev.id)),
        session=session,
        actor_user_id=owner.id,
    )
    assert entry.period_id is not None


@pytest.mark.asyncio
async def test_post_with_no_matching_period_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    # Bypass seed_owner's default period — wipe any pre-seeded periods.
    owner = await seed_owner(session)
    await session.execute(delete(AccountingPeriod))
    await session.flush()
    cash, rev = await _accounts(session)

    with pytest.raises(svc.NoMatchingPeriodError):
        await svc.post(
            svc.JournalEntryInput(description="x", posted_at=_now(), lines=_lines(cash.id, rev.id)),
            session=session,
            actor_user_id=owner.id,
        )


@pytest.mark.asyncio
async def test_post_into_closed_period_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    # Close the default period.
    p = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one()
    await periods_service.close(p.id, session=session, actor_user_id=owner.id)
    cash, rev = await _accounts(session)

    with pytest.raises(svc.PeriodNotOpenError):
        await svc.post(
            svc.JournalEntryInput(description="x", posted_at=_now(), lines=_lines(cash.id, rev.id)),
            session=session,
            actor_user_id=owner.id,
        )


@pytest.mark.asyncio
async def test_post_into_locked_period_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one()
    await periods_service.close(p.id, session=session, actor_user_id=owner.id)
    await periods_service.lock(p.id, session=session, actor_user_id=owner.id)
    cash, rev = await _accounts(session)

    with pytest.raises(svc.PeriodNotOpenError):
        await svc.post(
            svc.JournalEntryInput(description="x", posted_at=_now(), lines=_lines(cash.id, rev.id)),
            session=session,
            actor_user_id=owner.id,
        )


# Keep Base + Decimal symbols referenced so unused-import warnings don't
# bite.
_ = (Base, Decimal, AccountingPeriodState)
