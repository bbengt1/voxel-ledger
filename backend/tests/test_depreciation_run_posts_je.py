"""Depreciation run posts a balanced JE per planned entry (Phase 9.3, #155)."""

from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from app.models.fixed_asset import FixedAsset
from app.models.journal_entry import JournalEntry
from app.services import depreciation_run as run_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


def _end_of_current_month() -> date:
    today = datetime.now(UTC).date()
    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=last)


@pytest.mark.asyncio
async def test_run_posts_balanced_je(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts, cost="3600.00")  # 36 mo SL = 100/mo
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    period_end = _end_of_current_month()
    result = await run_service.run_for_period(session=app_session, period_end=period_end)
    assert result.posted_count == 1
    assert result.failed_count == 0

    entries = (
        (
            await app_session.execute(
                select(DepreciationScheduleEntry)
                .where(DepreciationScheduleEntry.asset_id == asset_id)
                .order_by(DepreciationScheduleEntry.period_index)
            )
        )
        .scalars()
        .all()
    )
    posted = [e for e in entries if e.state == DepreciationEntryState.POSTED]
    assert len(posted) == 1
    assert posted[0].journal_entry_id is not None

    je_id = posted[0].journal_entry_id
    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == je_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    lines = sorted(je.lines, key=lambda line: line.line_number)
    assert len(lines) == 2

    by_account = {line.account_id: line for line in lines}
    dep_exp_line = by_account[accounts["dep_exp_account_id"]]
    accum_line = by_account[accounts["accum_dep_account_id"]]
    assert dep_exp_line.debit == Decimal("100.000000")
    assert dep_exp_line.credit == Decimal("0")
    assert accum_line.credit == Decimal("100.000000")
    assert accum_line.debit == Decimal("0")

    asset = (
        await app_session.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
    ).scalar_one()
    assert asset.last_depreciated_on == posted[0].period_end
