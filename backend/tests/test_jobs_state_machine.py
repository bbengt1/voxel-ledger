"""Jobs state machine (Phase 5.2, #78; part-only since 8a).

Legal transitions:
  draft -> queued -> in_progress -> completed
  any non-terminal -> cancelled
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_part, token_for


async def _create_job(client, app_session) -> tuple[str, str]:
    part = await seed_part(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={"part_id": str(part.id), "quantity_ordered": 1},
    )
    return owner, r.json()["id"]


@pytest.mark.asyncio
async def test_full_happy_path(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
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
async def test_cancel_from_draft(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner, job_id = await _create_job(client, app_session)
    r = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_cannot_start_from_draft(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner, job_id = await _create_job(client, app_session)
    r = await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_complete_from_queued(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner, job_id = await _create_job(client, app_session)
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    r = await client.post(f"/api/v1/jobs/{job_id}/complete", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_submit_twice(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner, job_id = await _create_job(client, app_session)
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    r = await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_cancel_completed(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner, job_id = await _create_job(client, app_session)
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))
    await client.post(f"/api/v1/jobs/{job_id}/complete", headers=auth_header(owner))
    r = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 400
