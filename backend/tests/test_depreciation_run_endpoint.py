"""HTTP smoke for the operator-triggered depreciation-run endpoint (Phase 9.3, #155)."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime

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


def _end_of_current_month_iso() -> str:
    today = datetime.now(UTC).date()
    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=last).isoformat()


@pytest.mark.asyncio
async def test_endpoint_runs_and_returns_counts(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts)
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text

    resp = await client.post(
        "/api/v1/depreciation-runs",
        headers=auth_header(owner),
        json={"period_end": _end_of_current_month_iso()},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["period_end"] == _end_of_current_month_iso()
    assert payload["posted_count"] == 1
    assert payload["failed_count"] == 0


@pytest.mark.asyncio
async def test_endpoint_forbidden_for_viewer(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    viewer = await token_for(Role.VIEWER, client, app_session)
    resp = await client.post(
        "/api/v1/depreciation-runs",
        headers=auth_header(viewer),
        json={"period_end": _end_of_current_month_iso()},
    )
    assert resp.status_code == 403, resp.text
