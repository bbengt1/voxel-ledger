"""Recompute blocked once any entry is posted (Phase 9.2, #154)."""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from app.models.depreciation_schedule import (
    DepreciationEntryState,
    DepreciationScheduleEntry,
)
from app.services import depreciation_schedule as schedule_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_recompute_blocked_after_first_post(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts)
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    # Recompute on an all-planned schedule should succeed.
    rebuilt = await schedule_service.recompute(session=app_session, asset_id=asset_id)
    assert len(rebuilt) == 36
    await app_session.commit()

    # Flip one entry to ``posted`` manually.
    first = (
        (
            await app_session.execute(
                select(DepreciationScheduleEntry)
                .where(DepreciationScheduleEntry.asset_id == asset_id)
                .order_by(DepreciationScheduleEntry.period_index)
            )
        )
        .scalars()
        .first()
    )
    assert first is not None
    first.state = DepreciationEntryState.POSTED
    await app_session.commit()

    with pytest.raises(schedule_service.InvalidScheduleError):
        await schedule_service.recompute(session=app_session, asset_id=asset_id)
