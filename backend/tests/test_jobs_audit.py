"""Jobs/plates events surface in the audit projection (Phase 5.2, #78)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_product, token_for


def _payload(product_id: str) -> dict:
    return {
        "product_id": product_id,
        "quantity_ordered": 1,
        "plates": [{"name": "P1", "plate_number": 1, "parts_per_set": 1, "print_minutes": 0}],
    }


@pytest.mark.asyncio
async def test_job_created_event_in_audit(client: AsyncClient, app_session: AsyncSession) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    assert r.status_code == 201

    audit = await client.get(
        "/api/v1/admin/audit-log",
        headers=auth_header(owner),
        params={"event_type": "production.JobCreated"},
    )
    assert audit.status_code == 200, audit.text
    items = audit.json().get("items") or audit.json().get("rows") or []
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_job_state_events_in_audit(client: AsyncClient, app_session: AsyncSession) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    job_id = r.json()["id"]

    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_header(owner))

    for event_type in ("production.JobSubmitted", "production.JobCancelled"):
        audit = await client.get(
            "/api/v1/admin/audit-log",
            headers=auth_header(owner),
            params={"event_type": event_type},
        )
        assert audit.status_code == 200, audit.text
        items = audit.json().get("items") or audit.json().get("rows") or []
        assert len(items) >= 1, f"missing audit row for {event_type}"
