"""Late-fee-policies API surface tests (Phase 7.6, #114)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import auth_header, token_for


@pytest.mark.asyncio
async def test_create_and_list_global_policy(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/late-fee-policies",
        headers=auth_header(owner),
        json={
            "customer_id": None,
            "kind": "percent_of_outstanding",
            "amount": "0.015",
            "grace_period_days": 5,
            "apply_after_days": 30,
            "compound_interval_days": 30,
            "is_active": True,
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["kind"] == "percent_of_outstanding"
    assert body["customer_id"] is None

    listed = await client.get("/api/v1/late-fee-policies", headers=auth_header(owner))
    assert listed.status_code == 200
    assert any(p["id"] == body["id"] for p in listed.json()["items"])


@pytest.mark.asyncio
async def test_viewer_can_read_but_not_write(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    viewer = await token_for(Role.VIEWER, client, app_session)
    resp = await client.post(
        "/api/v1/late-fee-policies",
        headers=auth_header(viewer),
        json={"kind": "flat", "amount": "5"},
    )
    assert resp.status_code == 403
    listed = await client.get("/api/v1/late-fee-policies", headers=auth_header(viewer))
    assert listed.status_code == 200


@pytest.mark.asyncio
async def test_apply_now_returns_deferred_when_phase_74_absent(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    resp = await client.post(
        "/api/v1/late-fee-policies/apply-now",
        headers=auth_header(owner),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "applied" in body
    assert "deferred" in body
    # No fees today since nothing's overdue.
    assert body["deferred"] is True


@pytest.mark.asyncio
async def test_ar_aging_report_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    resp = await client.get("/api/v1/reports/ar-aging", headers=auth_header(owner))
    assert resp.status_code == 200
    body = resp.json()
    assert "bucket_days" in body
    assert "rows" in body
    assert "grand_total" in body

    csv_resp = await client.get("/api/v1/reports/ar-aging?format=csv", headers=auth_header(owner))
    assert csv_resp.status_code == 200
    assert "customer_number" in csv_resp.text
    assert csv_resp.headers["content-type"].startswith("text/csv")
