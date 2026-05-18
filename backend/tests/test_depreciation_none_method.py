"""Method=``none`` produces zero entries (Phase 9.2, #154)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.models.depreciation_schedule import DepreciationScheduleEntry
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
async def test_none_method_yields_no_schedule(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts, depreciation_method="none")
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    import uuid as _uuid

    asset_id = r.json()["id"]
    asset_uuid = _uuid.UUID(asset_id)

    rows = (
        (
            await app_session.execute(
                select(DepreciationScheduleEntry).where(
                    DepreciationScheduleEntry.asset_id == asset_uuid
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows == []

    api = await client.get(
        f"/api/v1/fixed-assets/{asset_id}/depreciation-schedule",
        headers=auth_header(owner),
    )
    assert api.status_code == 200, api.text
    assert api.json()["entries"] == []
