"""Scrap disposal: no proceeds, full book value to loss, state→written_off (Phase 9.4, #156)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.fixed_asset import FixedAsset, FixedAssetState
from httpx import AsyncClient
from sqlalchemy import select
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
async def test_dispose_scrap(client: AsyncClient, app_session: AsyncSession) -> None:
    await seed_wide_period(app_session)
    accounts = await seed_acquisition_stack(app_session)
    loss_acct = await seed_gain_loss_account(
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
    assert r.status_code == 201, r.text
    asset_id = uuid.UUID(r.json()["id"])

    # Only 6 months posted → $600 accumulated; book = $3000; loss = $3000.
    await mark_entries_posted_up_to(app_session, asset_id=asset_id, through_period_index=5)

    dispose_body = {
        "disposed_on": today.isoformat(),
        "kind": "scrap",
        "proceeds_amount": "0",
        "proceeds_account_id": None,
        "gain_loss_account_id": str(loss_acct.id),
    }
    resp = await client.post(
        f"/api/v1/fixed-assets/{asset_id}/dispose",
        headers=auth_header(owner),
        json=dispose_body,
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert Decimal(payload["accumulated_depreciation_at_disposal"]) == Decimal("600")
    assert Decimal(payload["book_value_at_disposal"]) == Decimal("3000")
    assert Decimal(payload["gain_loss_amount"]) == Decimal("-3000")
    assert payload["disposal_kind"] == "scrap"

    asset = (
        await app_session.execute(select(FixedAsset).where(FixedAsset.id == asset_id))
    ).scalar_one()
    await app_session.refresh(asset, ["state"])
    assert asset.state == FixedAssetState.WRITTEN_OFF
