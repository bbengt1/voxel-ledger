"""POST /fixed-assets/{id}/dispose returns 501 in Phase 9.1 (lands in 9.4)."""

from __future__ import annotations

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
async def test_dispose_returns_501(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/fixed-assets",
        headers=auth_header(owner),
        json=sample_acquire_body(accounts=accounts),
    )
    assert create.status_code == 201, create.text
    asset_id = create.json()["id"]

    r = await client.post(f"/api/v1/fixed-assets/{asset_id}/dispose", headers=auth_header(owner))
    assert r.status_code == 501
    assert "9.4" in r.json()["detail"]
