"""Job completion credits ``production_in`` on the related product.

When a job moves to ``completed``, pieces_produced should land on the
product's on-hand projection at the configured receiving location.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.services import inventory_alerts
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_product, token_for


async def _seed_workshop_location(session: AsyncSession) -> InventoryLocation:
    loc = InventoryLocation(
        id=uuid.uuid4(),
        code="WS01",
        name="Workshop",
        kind=InventoryLocationKind.WORKSHOP,
        is_archived=False,
    )
    session.add(loc)
    await session.commit()
    return loc


@pytest.mark.asyncio
async def test_complete_credits_product_on_hand(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_workshop_location(app_session)
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    # 1 plate × 2 parts/set, quantity_ordered=2 ⇒ 1 set required.
    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={
            "product_id": str(product.id),
            "quantity_ordered": 2,
            "plates": [
                {
                    "name": "P1",
                    "plate_number": 1,
                    "parts_per_set": 2,
                    "print_minutes": 0,
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]
    plate_id = create.json()["plates"][0]["id"]

    # Walk the state machine and record one plate run before completing.
    assert (await client.post(
        f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner)
    )).status_code == 200
    assert (await client.post(
        f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner)
    )).status_code == 200
    record = await client.post(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}/record-run",
        headers=auth_header(owner),
        json={"runs_completed_delta": 1},
    )
    assert record.status_code == 200, record.text

    # Pre-complete on-hand is zero for this product.
    before = await inventory_alerts.total_on_hand_for_entity(
        session=app_session, entity_kind="product", entity_id=product.id
    )
    assert before == 0

    complete = await client.post(
        f"/api/v1/jobs/{job_id}/complete", headers=auth_header(owner)
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["state"] == "completed"

    # ``parts_per_set * runs_completed`` = 2 pieces produced, credited to
    # the product's on-hand projection.
    after = await inventory_alerts.total_on_hand_for_entity(
        session=app_session, entity_kind="product", entity_id=product.id
    )
    assert int(after) == 2


@pytest.mark.asyncio
async def test_complete_with_zero_pieces_skips_inventory_write(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """A job completed without any recorded plate runs has 0 pieces and
    must not require a receiving location to exist."""
    # No workshop location seeded — proves the inventory path is only
    # touched when there are pieces to credit.
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={
            "product_id": str(product.id),
            "quantity_ordered": 1,
            "plates": [
                {
                    "name": "P1",
                    "plate_number": 1,
                    "parts_per_set": 1,
                    "print_minutes": 0,
                }
            ],
        },
    )
    job_id = create.json()["id"]
    for action in ("submit", "start", "complete"):
        r = await client.post(
            f"/api/v1/jobs/{job_id}/{action}", headers=auth_header(owner)
        )
        assert r.status_code == 200, (action, r.text)

    on_hand = await inventory_alerts.total_on_hand_for_entity(
        session=app_session, entity_kind="product", entity_id=product.id
    )
    assert on_hand == 0
