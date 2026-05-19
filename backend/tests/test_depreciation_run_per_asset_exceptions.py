"""One bad asset doesn't block the rest of the depreciation run (Phase 9.3, #155)."""

from __future__ import annotations

import calendar
import uuid
from datetime import UTC, date, datetime

import pytest
from app.models.auth import Role
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from app.models.fixed_asset import FixedAsset
from app.services import depreciation_run as run_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
async def test_per_asset_exception_does_not_block_rest(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body_good = sample_acquire_body(accounts=accounts, name="Good Asset")
    r1 = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body_good)
    assert r1.status_code == 201, r1.text
    good_id = uuid.UUID(r1.json()["id"])

    body_bad = sample_acquire_body(accounts=accounts, name="Bad Asset")
    r2 = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body_bad)
    assert r2.status_code == 201, r2.text
    bad_id = uuid.UUID(r2.json()["id"])

    # Poison the "bad" asset: point its depreciation_expense_account_id at a
    # non-existent account so the JE post raises AccountNotFoundError.
    bad_asset = (
        await app_session.execute(select(FixedAsset).where(FixedAsset.id == bad_id))
    ).scalar_one()
    bad_asset.depreciation_expense_account_id = uuid.uuid4()
    await app_session.commit()

    period_end = _end_of_current_month()
    result = await run_service.run_for_period(session=app_session, period_end=period_end)
    assert result.posted_count == 1
    assert result.failed_count == 1

    posted = (
        (
            await app_session.execute(
                select(DepreciationScheduleEntry).where(
                    DepreciationScheduleEntry.state == DepreciationEntryState.POSTED
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(posted) == 1
    assert posted[0].asset_id == good_id

    # The bad asset's entry stays planned.
    bad_entries = (
        (
            await app_session.execute(
                select(DepreciationScheduleEntry).where(
                    DepreciationScheduleEntry.asset_id == bad_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert all(e.state == DepreciationEntryState.PLANNED for e in bad_entries)
