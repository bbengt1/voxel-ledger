"""Disposal flips any future planned schedule entries to ``adjusted`` (Phase 9.4, #156)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from app.models.depreciation_schedule import DepreciationEntryState
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._asset_disposal_helpers import (
    fetch_entries,
    mark_entries_posted_up_to,
    seed_gain_loss_account,
    seed_wide_period,
    shift_months,
)
from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_dispose_cancels_future_planned_entries(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await seed_wide_period(app_session)
    accounts = await seed_acquisition_stack(app_session)
    loss = await seed_gain_loss_account(
        app_session, code="7100", name="Loss on Disposal", kind="expense"
    )
    owner = await token_for(Role.OWNER, client, app_session)

    today = datetime.now(UTC).date()
    body = sample_acquire_body(
        accounts=accounts,
        cost="3600.00",
        acquired_on=shift_months(today, -13).isoformat(),
    )
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    # 12 of the 36 entries are posted; 24 remain planned.
    await mark_entries_posted_up_to(app_session, asset_id=asset_id, through_period_index=11)

    dispose_body = {
        "disposed_on": today.isoformat(),
        "kind": "scrap",
        "proceeds_amount": "0",
        "proceeds_account_id": None,
        "gain_loss_account_id": str(loss.id),
    }
    resp = await client.post(
        f"/api/v1/fixed-assets/{asset_id}/dispose",
        headers=auth_header(owner),
        json=dispose_body,
    )
    assert resp.status_code == 201, resp.text

    entries = await fetch_entries(app_session, asset_id)
    posted = [e for e in entries if e.state == DepreciationEntryState.POSTED]
    adjusted = [e for e in entries if e.state == DepreciationEntryState.ADJUSTED]
    planned = [e for e in entries if e.state == DepreciationEntryState.PLANNED]

    assert len(posted) == 12
    # Every entry past the disposal date is flipped.
    assert len(adjusted) > 0
    # Anything still ``planned`` would have had period_end <= disposed_on,
    # which can happen for entries inside the disposal month — those aren't
    # cancelled because the operator already chose not to post them.
    for entry in planned:
        assert entry.period_end <= today
