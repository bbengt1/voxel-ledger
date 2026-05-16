"""Bills CRUD + role matrix (Phase 8.2, #129)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bills_helpers import (
    auth_header,
    sample_bill_body,
    seed_full_ap_stack,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_create_get_list_bill(client: AsyncClient, app_session: AsyncSession) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    r = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    assert r.status_code == 201, r.text
    bill = r.json()
    assert bill["bill_number"].startswith("BILL-")
    assert bill["state"] == "draft"
    assert bill["total_amount"] == "20.000000"
    assert bill["posting_journal_entry_id"] is None
    assert len(bill["items"]) == 1

    r2 = await client.get(f"/api/v1/bills/{bill['id']}", headers=auth_header(owner))
    assert r2.status_code == 200
    assert r2.json()["bill_number"] == bill["bill_number"]

    r3 = await client.get("/api/v1/bills", headers=auth_header(owner))
    assert r3.status_code == 200
    items = r3.json()["items"]
    assert any(i["id"] == bill["id"] for i in items)


@pytest.mark.asyncio
async def test_update_only_legal_in_draft(client: AsyncClient, app_session: AsyncSession) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_stack(app_session)
    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    bill_id = create.json()["id"]

    upd = await client.patch(
        f"/api/v1/bills/{bill_id}",
        headers=auth_header(owner),
        json={"notes": "updated"},
    )
    assert upd.status_code == 200
    assert upd.json()["notes"] == "updated"

    issued = await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    assert issued.json()["state"] == "issued"

    upd2 = await client.patch(
        f"/api/v1/bills/{bill_id}",
        headers=auth_header(owner),
        json={"notes": "after-issue"},
    )
    assert upd2.status_code == 400


@pytest.mark.asyncio
async def test_viewer_can_read_but_not_write(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    bill_id = create.json()["id"]
    viewer = await token_for(Role.VIEWER, client, app_session)

    r_get = await client.get(f"/api/v1/bills/{bill_id}", headers=auth_header(viewer))
    assert r_get.status_code == 200

    r_post = await client.post(
        "/api/v1/bills",
        headers=auth_header(viewer),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    assert r_post.status_code == 403

    r_issue = await client.post(f"/api/v1/bills/{bill_id}/issue", headers=auth_header(viewer))
    assert r_issue.status_code == 403


@pytest.mark.asyncio
async def test_sales_role_cannot_write(client: AsyncClient, app_session: AsyncSession) -> None:
    """Sales role is read-only for AP — write is owner + bookkeeper only."""
    vendor = await seed_vendor(app_session)
    sales = await token_for(Role.SALES, client, app_session)
    r = await client.post(
        "/api/v1/bills",
        headers=auth_header(sales),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_production_role_cannot_write(client: AsyncClient, app_session: AsyncSession) -> None:
    vendor = await seed_vendor(app_session)
    prod = await token_for(Role.PRODUCTION, client, app_session)
    r = await client.post(
        "/api/v1/bills",
        headers=auth_header(prod),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    assert r.status_code == 403
