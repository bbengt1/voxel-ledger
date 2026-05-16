"""Clear error when AP posting settings unset (Phase 8.2, #129)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bills_helpers import (
    auth_header,
    sample_bill_body,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_issue_without_settings_returns_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    vendor = await seed_vendor(app_session)
    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    bill_id = create.json()["id"]

    r = await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(owner))
    assert r.status_code == 400
    assert "configure default AP posting accounts" in r.json()["detail"]
