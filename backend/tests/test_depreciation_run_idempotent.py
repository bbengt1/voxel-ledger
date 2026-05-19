"""Depreciation run is idempotent: re-running for the same period is a no-op (Phase 9.3, #155)."""

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
async def test_run_idempotent(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts)
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    period_end = _end_of_current_month()
    first = await run_service.run_for_period(session=app_session, period_end=period_end)
    assert first.posted_count == 1

    second = await run_service.run_for_period(session=app_session, period_end=period_end)
    assert second.posted_count == 0
    assert second.failed_count == 0

    posted = (
        (
            await app_session.execute(
                select(DepreciationScheduleEntry)
                .where(DepreciationScheduleEntry.asset_id == asset_id)
                .where(DepreciationScheduleEntry.state == DepreciationEntryState.POSTED)
            )
        )
        .scalars()
        .all()
    )
    assert len(posted) == 1
