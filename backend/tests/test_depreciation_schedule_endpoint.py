"""HTTP smoke for the depreciation-schedule GET endpoint (Phase 9.2, #154)."""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_get_schedule_returns_entries(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts)
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = r.json()["id"]

    resp = await client.get(
        f"/api/v1/fixed-assets/{asset_id}/depreciation-schedule",
        headers=auth_header(owner),
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["asset_id"] == asset_id
    assert len(payload["entries"]) == 36
    indexes = [e["period_index"] for e in payload["entries"]]
    assert indexes == list(range(36))
    # Total should equal the depreciable basis (cost 1200, salvage 0).
    from decimal import Decimal as _D

    assert _D(payload["total_depreciation"]) == _D("1200.00")


@pytest.mark.asyncio
async def test_get_schedule_404_for_unknown_asset(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    bogus = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/fixed-assets/{bogus}/depreciation-schedule",
        headers=auth_header(owner),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_get_schedule_viewer_can_read(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    viewer = await token_for(Role.VIEWER, client, app_session)

    body = sample_acquire_body(accounts=accounts)
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    asset_id = r.json()["id"]

    resp = await client.get(
        f"/api/v1/fixed-assets/{asset_id}/depreciation-schedule",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 200, resp.text
