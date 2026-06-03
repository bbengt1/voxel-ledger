"""Jobs produce Parts: part_id, recipe snapshot, completion credits part
stock (assembly-line epic #267 Phase 4a)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.inventory_on_hand import InventoryOnHand
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services import parts as parts_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import seed_printer


async def _token(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-{uuid.uuid4().hex[:6]}@example.com"
    await create_user(
        session, email=email, password="pw", full_name="t", role=role, bcrypt_rounds=4
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _part_with_material(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    m = await materials_service.create(
        session,
        name=f"PLA {uuid.uuid4().hex[:6]}",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await session.commit()
    await receipts_service.record(
        session,
        material_id=m.id,
        grams=Decimal("1000"),
        total_cost=Decimal("20"),
        actor_user_id=None,
    )  # $0.02/g
    await session.commit()
    printer = await seed_printer(session)
    part = await parts_service.create(
        session,
        name="Bracket",
        print_minutes=60,
        setup_minutes=0,
        parts_per_run=2,
        print_grams_by_material={m.id: Decimal("50")},
        assigned_printer_ids=[printer.id],
        actor_user_id=None,
    )
    await session.commit()
    return part.id, m.id


@pytest.mark.asyncio
async def test_create_job_for_part_snapshots_recipe(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    part_id, material_id = await _part_with_material(app_session)

    r = await client.post(
        "/api/v1/jobs",
        headers=_h(owner),
        json={"part_id": str(part_id), "quantity_ordered": 2},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["part_id"] == str(part_id)
    assert body["product_id"] is None
    # The recipe is snapshotted into a single plate.
    assert len(body["plates"]) == 1
    plate = body["plates"][0]
    assert plate["parts_per_set"] == 2
    assert plate["print_minutes"] == 60
    assert plate["print_grams_by_material"][str(material_id)] == "50"


@pytest.mark.asyncio
async def test_part_job_completion_credits_part_stock(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    part_id, _m = await _part_with_material(app_session)

    create = await client.post(
        "/api/v1/jobs",
        headers=_h(owner),
        json={"part_id": str(part_id), "quantity_ordered": 2},
    )
    job_id = create.json()["id"]
    plate_id = create.json()["plates"][0]["id"]

    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=_h(owner))
    await client.post(f"/api/v1/jobs/{job_id}/start", headers=_h(owner))
    # One run → parts_per_run (2) pieces.
    run = await client.post(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}/record-run",
        headers=_h(owner),
        json={"runs_completed_delta": 1},
    )
    assert run.status_code == 200, run.text
    done = await client.post(f"/api/v1/jobs/{job_id}/complete", headers=_h(owner))
    assert done.status_code == 200, done.text
    assert done.json()["pieces_produced"] == 2

    # Part stock credited (entity_kind='part').
    rows = (
        await app_session.execute(
            select(InventoryOnHand.on_hand).where(
                InventoryOnHand.entity_kind == "part",
                InventoryOnHand.entity_id == part_id,
            )
        )
    ).all()
    assert sum((r[0] for r in rows), Decimal("0")) == Decimal("2")


@pytest.mark.asyncio
async def test_part_job_live_cost_from_part(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    part_id, _m = await _part_with_material(app_session)
    create = await client.post(
        "/api/v1/jobs",
        headers=_h(owner),
        json={"part_id": str(part_id), "quantity_ordered": 2},
    )
    job_id = create.json()["id"]
    cost = await client.post("/api/v1/jobs/calculate", headers=_h(owner), json={"job_id": job_id})
    assert cost.status_code == 200, cost.text
    # 50 g * $0.02 = $1.00 material across the 2-piece run; no supplies.
    assert Decimal(cost.json()["material_cost"]) == Decimal("1.00")
    assert Decimal(cost.json()["supply_cost"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_job_requires_part_or_product(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    r = await client.post("/api/v1/jobs", headers=_h(owner), json={"quantity_ordered": 1})
    assert r.status_code == 422, r.text
