"""CRUD smoke for fixed assets (Phase 9.1, #153)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    seed_intangible_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_acquire_creates_active_asset(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    r = await client.post(
        "/api/v1/fixed-assets",
        headers=auth_header(owner),
        json=sample_acquire_body(accounts=accounts),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "active"
    assert body["asset_number"].startswith("ASSET-")
    # QBO is the sole ledger (epic #312, Phase 5e): the acquisition is pushed
    # via the QBO sync outbox; no local JE id is stamped.
    assert body["posting_journal_entry_id"] is None


@pytest.mark.asyncio
async def test_patch_updates_metadata_only(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    r = await client.post(
        "/api/v1/fixed-assets",
        headers=auth_header(owner),
        json=sample_acquire_body(accounts=accounts),
    )
    assert r.status_code == 201, r.text
    asset_id = r.json()["id"]

    patch = await client.patch(
        f"/api/v1/fixed-assets/{asset_id}",
        headers=auth_header(owner),
        json={"name": "Renamed Asset", "serial_number": "SN-001"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["name"] == "Renamed Asset"
    assert patch.json()["serial_number"] == "SN-001"

    # Cost is not in the allowed update set; FastAPI's pydantic rejects
    # the unknown field at the schema layer (model has extra="ignore" by
    # default, so the extra field is silently dropped — and no JE
    # changes). Verify the cost is unchanged.
    refresh = await client.get(f"/api/v1/fixed-assets/{asset_id}", headers=auth_header(owner))
    assert refresh.json()["acquisition_cost"] == "1200.000000"


@pytest.mark.asyncio
async def test_list_with_filters(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    intangibles = await seed_intangible_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    r1 = await client.post(
        "/api/v1/fixed-assets",
        headers=auth_header(owner),
        json=sample_acquire_body(accounts=accounts, asset_class="computer"),
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        "/api/v1/fixed-assets",
        headers=auth_header(owner),
        json=sample_acquire_body(
            accounts=intangibles,
            kind="intangible",
            asset_class="software",
            name="Adobe Suite",
        ),
    )
    assert r2.status_code == 201, r2.text

    listing = await client.get(
        "/api/v1/fixed-assets",
        headers=auth_header(owner),
        params={"kind": "intangible"},
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "intangible"
    assert items[0]["name"] == "Adobe Suite"

    search = await client.get(
        "/api/v1/fixed-assets",
        headers=auth_header(owner),
        params={"search": "Adobe"},
    )
    assert search.status_code == 200
    assert len(search.json()["items"]) == 1
