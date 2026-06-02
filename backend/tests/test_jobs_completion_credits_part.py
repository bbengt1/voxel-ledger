"""Job completion credits ``production_in`` on the related part (Phase 8a).

When a job moves to ``completed``, pieces_produced should land on the
part's on-hand projection at the configured receiving location.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.models.inventory_on_hand import InventoryOnHand
from app.services import inventory_alerts
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_part, token_for


@pytest.mark.asyncio
async def test_complete_credits_part_on_hand(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    part = await seed_part(app_session, parts_per_run=2)
    owner = await token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={
            "part_id": str(part.id),
            "quantity_ordered": 2,
        },
    )
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]
    plate_id = create.json()["plates"][0]["id"]

    # Walk the state machine and record one plate run before completing.
    assert (
        await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))
    ).status_code == 200
    record = await client.post(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}/record-run",
        headers=auth_header(owner),
        json={"runs_completed_delta": 1},
    )
    assert record.status_code == 200, record.text

    # Pre-complete on-hand is zero for this part.
    before = await inventory_alerts.total_on_hand_for_entity(
        session=app_session, entity_kind="part", entity_id=part.id
    )
    assert before == 0

    complete = await client.post(f"/api/v1/jobs/{job_id}/complete", headers=auth_header(owner))
    assert complete.status_code == 200, complete.text
    assert complete.json()["state"] == "completed"

    # ``parts_per_run * runs_completed`` = 2 pieces produced, credited to
    # the part's on-hand projection.
    after = await inventory_alerts.total_on_hand_for_entity(
        session=app_session, entity_kind="part", entity_id=part.id
    )
    assert int(after) == 2

    # Also verify the InventoryOnHand row uses entity_kind='part'.
    rows = (
        await app_session.execute(
            select(InventoryOnHand.entity_kind, InventoryOnHand.on_hand).where(
                InventoryOnHand.entity_kind == "part",
                InventoryOnHand.entity_id == part.id,
            )
        )
    ).all()
    assert len(rows) >= 1
    assert all(row[0] == "part" for row in rows)


@pytest.mark.asyncio
async def test_complete_with_zero_pieces_skips_inventory_write(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    """A job completed without any recorded plate runs has 0 pieces and
    must not write any inventory_on_hand row."""
    part = await seed_part(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={
            "part_id": str(part.id),
            "quantity_ordered": 1,
        },
    )
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]
    for action in ("submit", "start", "complete"):
        r = await client.post(f"/api/v1/jobs/{job_id}/{action}", headers=auth_header(owner))
        assert r.status_code == 200, (action, r.text)

    on_hand = await inventory_alerts.total_on_hand_for_entity(
        session=app_session, entity_kind="part", entity_id=part.id
    )
    assert on_hand == 0
