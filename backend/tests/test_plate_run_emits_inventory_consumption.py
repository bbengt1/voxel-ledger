"""Plate-run + inventory.production_consumption coupling (Phase 5.2, #78).

Recording a plate run produces, in the SAME transaction:
  - one ``production.PlateRunRecorded`` event
  - one ``inventory.TransactionRecorded`` with ``kind=production_consumption``
    per material in ``plate.print_grams_by_material``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services import materials as materials_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_product, token_for


@pytest.mark.asyncio
async def test_plate_run_drains_materials(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    product = await seed_product(app_session)
    mat = await materials_service.create(
        app_session,
        name="PLA Black",
        brand="X",
        material_type="PLA",
        color="black",
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    await app_session.commit()

    owner = await token_for(Role.OWNER, client, app_session)
    payload = {
        "product_id": str(product.id),
        "quantity_ordered": 1,
        "plates": [
            {
                "name": "P1",
                "plate_number": 1,
                "parts_per_set": 2,
                "print_minutes": 30,
                "print_grams_by_material": {str(mat.id): "42.5"},
            }
        ],
    }
    r = await client.post("/api/v1/jobs", headers=auth_header(owner), json=payload)
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    plate_id = r.json()["plates"][0]["id"]

    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))

    run = await client.post(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}/record-run",
        headers=auth_header(owner),
        json={"runs_completed_delta": 1},
    )
    assert run.status_code == 200, run.text
    assert run.json()["runs_completed"] == 1

    # Inspect inventory_transactions for the new production_consumption row.
    from app.models.inventory_transaction import InventoryTransaction

    stmt = select(InventoryTransaction).where(InventoryTransaction.kind == "production_consumption")
    rows = list((await app_session.execute(stmt)).scalars().all())
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_kind == "material"
    assert row.entity_id == mat.id
    # Outbound direction → negative quantity (magnitude 42.5).
    assert row.quantity == Decimal("-42.5")
    assert row.linked_job_id is not None
    assert str(row.linked_job_id) == job_id

    # And the event got recorded.
    from app.models.event import Event

    stmt = select(Event).where(Event.type == "inventory.TransactionRecorded")
    events = list((await app_session.execute(stmt)).scalars().all())
    assert len(events) >= 1
    assert any(e.payload.get("kind") == "production_consumption" for e in events)

    # And the production.PlateRunRecorded event got emitted.
    stmt = select(Event).where(Event.type == "production.PlateRunRecorded")
    plate_events = list((await app_session.execute(stmt)).scalars().all())
    assert len(plate_events) == 1
    consumed = plate_events[0].payload.get("materials_consumed") or []
    assert len(consumed) == 1
    assert consumed[0]["material_id"] == str(mat.id)
    assert consumed[0]["grams"] == "42.5"


@pytest.mark.asyncio
async def test_plate_run_with_multiple_runs_delta(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    product = await seed_product(app_session)
    mat = await materials_service.create(
        app_session,
        name="PLA Red",
        brand="X",
        material_type="PLA",
        color="red",
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    await app_session.commit()

    owner = await token_for(Role.OWNER, client, app_session)
    payload = {
        "product_id": str(product.id),
        "quantity_ordered": 1,
        "plates": [
            {
                "name": "P1",
                "plate_number": 1,
                "parts_per_set": 1,
                "print_minutes": 0,
                "print_grams_by_material": {str(mat.id): "10"},
            }
        ],
    }
    r = await client.post("/api/v1/jobs", headers=auth_header(owner), json=payload)
    job_id = r.json()["id"]
    plate_id = r.json()["plates"][0]["id"]
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    await client.post(f"/api/v1/jobs/{job_id}/start", headers=auth_header(owner))

    run = await client.post(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}/record-run",
        headers=auth_header(owner),
        json={"runs_completed_delta": 3},
    )
    assert run.status_code == 200
    assert run.json()["runs_completed"] == 3

    from app.models.inventory_transaction import InventoryTransaction

    stmt = select(InventoryTransaction).where(InventoryTransaction.kind == "production_consumption")
    rows = list((await app_session.execute(stmt)).scalars().all())
    # One row per call; magnitude = grams_per_run * delta.
    assert len(rows) == 1
    assert rows[0].quantity == Decimal("-30")
