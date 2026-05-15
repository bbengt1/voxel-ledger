"""Jobs state machine (Phase 5.2, #78).

Legal transitions:
  draft -> queued -> in_progress -> completed
  any non-terminal -> cancelled
"""

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


async def _create_job(client, app_session) -> tuple[str, str]:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    return owner, r.json()["id"]


@pytest.mark.asyncio
async def test_full_happy_path(client: AsyncClient, app_session: AsyncSession) -> None:
    owner, job_id = await _create_job(client, app_session)

    for action, expected in [
        ("submit", "queued"),
        ("start", "in_progress"),
        ("complete", "completed"),
    ]:
        r = await client.post(f"/api/v1/jobs/{job_id}/{action}", headers=auth_header(owner))
        assert r.status_code == 200, r.text
        assert r.json()["state"] == expected


@pytest.mark.asyncio
async def test_cancel_from_draft(client: AsyncClient, app_session: AsyncSession) -> None:
    owner, job_id = await _create_job(client, app_session)
    r = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_cannot_start_from_draft(client: AsyncClient, app_session: AsyncSession) -> None:
    owner, job_id = await _create_job(client, app_session)
    r = await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_complete_from_queued(client: AsyncClient, app_session: AsyncSession) -> None:
    owner, job_id = await _create_job(client, app_session)
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    r = await client.post(f"/api/v1/jobs/{job_id}/complete", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_submit_twice(client: AsyncClient, app_session: AsyncSession) -> None:
    owner, job_id = await _create_job(client, app_session)
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    r = await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_cancel_completed(client: AsyncClient, app_session: AsyncSession) -> None:
    owner, job_id = await _create_job(client, app_session)
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))
    await client.post(f"/api/v1/jobs/{job_id}/complete", headers=auth_header(owner))
    r = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 400
