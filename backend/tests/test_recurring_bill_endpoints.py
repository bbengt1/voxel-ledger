"""Phase 8.5 (#132): recurring bills API + role matrix."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._recurring_bills_helpers import (
    auth_header,
    sample_template_body,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_create_get_list_template(client: AsyncClient, app_session: AsyncSession) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_template_body(vendor_id=str(vendor.id))
    r = await client.post(
        "/api/v1/recurring-bills",
        headers=auth_header(owner),
        json=body,
    )
    assert r.status_code == 201, r.text
    tpl = r.json()
    assert tpl["state"] == "active"
    assert tpl["cadence_kind"] == "monthly"
    assert tpl["auto_issue"] is False
    assert tpl["next_issue_at"] is not None
    assert len(tpl["items"]) == 1

    r2 = await client.get(f"/api/v1/recurring-bills/{tpl['id']}", headers=auth_header(owner))
    assert r2.status_code == 200

    r3 = await client.get("/api/v1/recurring-bills", headers=auth_header(owner))
    assert r3.status_code == 200
    assert any(i["id"] == tpl["id"] for i in r3.json()["items"])


@pytest.mark.asyncio
async def test_role_matrix(client: AsyncClient, app_session: AsyncSession) -> None:
    vendor = await seed_vendor(app_session)
    owner_token = await token_for(Role.OWNER, client, app_session)
    viewer_token = await token_for(Role.VIEWER, client, app_session)
    sales_token = await token_for(Role.SALES, client, app_session)

    body = sample_template_body(vendor_id=str(vendor.id))
    # Viewer cannot create
    r = await client.post(
        "/api/v1/recurring-bills",
        headers=auth_header(viewer_token),
        json=body,
    )
    assert r.status_code == 403

    # Sales cannot create (AP write is owner + bookkeeper)
    r = await client.post(
        "/api/v1/recurring-bills",
        headers=auth_header(sales_token),
        json=body,
    )
    assert r.status_code == 403

    # Owner creates
    r = await client.post(
        "/api/v1/recurring-bills",
        headers=auth_header(owner_token),
        json=body,
    )
    assert r.status_code == 201
    tpl_id = r.json()["id"]

    # Viewer can read
    r = await client.get(f"/api/v1/recurring-bills/{tpl_id}", headers=auth_header(viewer_token))
    assert r.status_code == 200

    # Viewer cannot pause
    r = await client.post(
        f"/api/v1/recurring-bills/{tpl_id}/pause",
        headers=auth_header(viewer_token),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_pause_resume_cancel_endpoints(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    body = sample_template_body(vendor_id=str(vendor.id))
    r = await client.post("/api/v1/recurring-bills", headers=auth_header(owner), json=body)
    tpl_id = r.json()["id"]

    r = await client.post(f"/api/v1/recurring-bills/{tpl_id}/pause", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.json()["state"] == "paused"

    r = await client.post(f"/api/v1/recurring-bills/{tpl_id}/resume", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.json()["state"] == "active"

    r = await client.post(f"/api/v1/recurring-bills/{tpl_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient, app_session: AsyncSession) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    body = sample_template_body(vendor_id=str(vendor.id))
    r = await client.post("/api/v1/recurring-bills", headers=auth_header(owner), json=body)
    tpl_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/recurring-bills/{tpl_id}",
        headers=auth_header(owner),
        json={"name": "Renamed lease", "cadence_interval": 3},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed lease"
    assert r.json()["cadence_interval"] == 3


@pytest.mark.asyncio
async def test_materialize_now_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    future_start = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    body = sample_template_body(vendor_id=str(vendor.id), start_at=future_start)
    r = await client.post("/api/v1/recurring-bills", headers=auth_header(owner), json=body)
    tpl_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/recurring-bills/{tpl_id}/materialize-now",
        headers=auth_header(owner),
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["template_id"] == tpl_id
    assert payload["bill_number"].startswith("BILL-")
