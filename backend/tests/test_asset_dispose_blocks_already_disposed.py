"""Re-disposing an asset is blocked with 409 (Phase 9.4, #156)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._asset_disposal_helpers import (
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
async def test_dispose_blocks_already_disposed(
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
        acquired_on=shift_months(today, -7).isoformat(),
    )
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201
    asset_id = uuid.UUID(r.json()["id"])

    await mark_entries_posted_up_to(app_session, asset_id=asset_id, through_period_index=5)

    dispose_body = {
        "disposed_on": today.isoformat(),
        "kind": "scrap",
        "proceeds_amount": "0",
        "proceeds_account_id": None,
        "gain_loss_account_id": str(loss.id),
    }
    first = await client.post(
        f"/api/v1/fixed-assets/{asset_id}/dispose",
        headers=auth_header(owner),
        json=dispose_body,
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/api/v1/fixed-assets/{asset_id}/dispose",
        headers=auth_header(owner),
        json=dispose_body,
    )
    assert second.status_code == 409, second.text
