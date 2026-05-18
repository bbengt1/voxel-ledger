"""Same-TX schedule generation on acquire (Phase 9.2, #154)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from app.models.auth import Role
from app.models.depreciation_schedule import DepreciationScheduleEntry
from app.models.fixed_asset import FixedAsset
from app.services import depreciation_schedule as schedule_service
from app.services import fixed_assets as fa_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    seed_user,
    token_for,
)


@pytest.mark.asyncio
async def test_acquire_generates_schedule(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts)  # 36-month straight_line, cost 1200
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    rows = (
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
    assert len(rows) == 36
    assert rows[0].period_index == 0
    assert rows[-1].period_index == 35
    total = sum((r.depreciation_amount for r in rows), Decimal("0"))
    assert total == Decimal("1200.00")
    # All planned at creation time.
    assert {r.state.value for r in rows} == {"planned"}


@pytest.mark.asyncio
async def test_acquire_rollback_rolls_back_schedule(app_session: AsyncSession) -> None:
    """If the schedule generator raises, the whole acquisition rolls back —
    no FixedAsset row, no schedule rows."""
    accounts = await seed_acquisition_stack(app_session)
    user = await seed_user(app_session, email="rollback@example.com")

    # Patch generate to raise so the whole TX rolls back.
    with patch.object(
        schedule_service,
        "generate",
        side_effect=schedule_service.InvalidScheduleError("boom"),
    ):
        with pytest.raises(schedule_service.InvalidScheduleError):
            await fa_service.acquire(
                session=app_session,
                name="Will Roll Back",
                kind="tangible",
                asset_class="computer",
                acquired_on=datetime.now(UTC).date(),
                acquisition_cost=Decimal("1200.00"),
                salvage_value=Decimal("0"),
                useful_life_months=36,
                depreciation_method="straight_line",
                asset_account_id=accounts["asset_account_id"],
                accumulated_depreciation_account_id=accounts["accum_dep_account_id"],
                depreciation_expense_account_id=accounts["dep_exp_account_id"],
                contra_account_id=accounts["bank_account_id"],
                actor_user_id=user.id,
            )
        await app_session.rollback()

    # Neither table should contain the in-flight row.
    assets = (
        (await app_session.execute(select(FixedAsset).where(FixedAsset.name == "Will Roll Back")))
        .scalars()
        .all()
    )
    assert assets == []
    schedule_rows = (await app_session.execute(select(DepreciationScheduleEntry))).scalars().all()
    assert schedule_rows == []
    # Keep the unused import quiet.
    _ = datetime.now(UTC)
