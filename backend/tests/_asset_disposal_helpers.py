"""Shared helpers for fixed-asset disposal tests (Phase 9.4, #156)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.account import Account
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_wide_period(session: AsyncSession) -> AccountingPeriod:
    """Create a single open period covering 2 years back to 1 year forward.

    Many disposal tests acquire an asset a year ago and dispose it today, so
    the standard ±60-day window used by ``_fixed_assets_helpers`` isn't wide
    enough. Call this BEFORE ``seed_acquisition_stack`` so the latter skips
    its own narrow-period creation.
    """
    today = datetime.now(UTC).date()
    period = AccountingPeriod(
        id=uuid.uuid4(),
        name="phase94-wide-test-period",
        start_date=today - timedelta(days=730),
        end_date=today + timedelta(days=365),
        state=AccountingPeriodState.OPEN.value,
    )
    session.add(period)
    await session.flush()
    await session.commit()
    return period


async def seed_gain_loss_account(
    session: AsyncSession,
    *,
    code: str = "7000",
    name: str = "Gain/Loss on Disposal",
    kind: str = "revenue",
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type=kind)
    session.add(acct)
    await session.flush()
    await session.commit()
    return acct


async def mark_entries_posted_up_to(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    through_period_index: int,
) -> None:
    """Flip the first ``through_period_index + 1`` planned schedule entries
    to ``posted`` so the disposal flow can snapshot accumulated depreciation.

    No JE is posted — this is purely a test hack to populate the schedule
    state that Phase 9.3 would normally produce.
    """
    await session.execute(
        update(DepreciationScheduleEntry)
        .where(DepreciationScheduleEntry.asset_id == asset_id)
        .where(DepreciationScheduleEntry.period_index <= through_period_index)
        .values(state=DepreciationEntryState.POSTED)
    )
    await session.flush()
    await session.commit()


async def fetch_entries(
    session: AsyncSession, asset_id: uuid.UUID
) -> list[DepreciationScheduleEntry]:
    rows = (
        (
            await session.execute(
                select(DepreciationScheduleEntry)
                .where(DepreciationScheduleEntry.asset_id == asset_id)
                .order_by(DepreciationScheduleEntry.period_index)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def shift_months(d: date, months: int) -> date:
    """Naive month shift used for tests (no day clamping needed)."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    return date(year, month, d.day if d.day <= 28 else 28)
