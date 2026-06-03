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

from tests._jobs_helpers import auth_header, seed_part, seed_printer, token_for


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
async def test_start_requires_a_printer_assignment(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    """A queued job with no printer on any plate cannot be started; assigning
    a printer unblocks it."""
    part = await seed_part(app_session, with_printer=False)
    owner = await token_for(Role.OWNER, client, app_session)
    created = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={"part_id": str(part.id), "quantity_ordered": 1},
    )
    job = created.json()
    job_id = job["id"]
    plate_id = job["plates"][0]["id"]

    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))

    # No printer assigned → start is rejected.
    blocked = await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))
    assert blocked.status_code == 400, blocked.text
    assert "printer" in blocked.json()["detail"].lower()
    got = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_header(owner))
    assert got.json()["state"] == "queued"  # state unchanged

    # Assign a printer, then start succeeds.
    printer = await seed_printer(app_session)
    assigned = await client.post(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}/assign-printer",
        headers=auth_header(owner),
        json={"printer_id": str(printer.id)},
    )
    assert assigned.status_code == 200, assigned.text

    started = await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "in_progress"


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
