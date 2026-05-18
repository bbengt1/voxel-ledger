"""Account-type validation on fixed-asset acquire (Phase 9.1, #153)."""

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
async def test_asset_account_must_be_asset_type(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts)
    # Swap asset_account_id with the depreciation_expense_account_id
    # (which is an expense account) — must be rejected.
    body["asset_account_id"] = str(accounts["dep_exp_account_id"])

    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 400, r.text
    assert "expected" in r.json()["detail"]


@pytest.mark.asyncio
async def test_dep_expense_account_must_be_expense_type(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts)
    # The bank account is type=asset, not expense.
    body["depreciation_expense_account_id"] = str(accounts["bank_account_id"])

    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 400
    assert "expected" in r.json()["detail"]
