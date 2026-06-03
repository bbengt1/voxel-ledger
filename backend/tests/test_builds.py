"""Build / assembly: consume parts + supplies, credit product, capture
assembly labor (assembly-line epic #267 Phase 5a)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.inventory_on_hand import InventoryOnHand
from app.services import bom as bom_service
from app.services import inventory_transactions as inventory_tx_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services import parts as parts_service
from app.services import products as products_service
from app.services import supplies as supplies_service
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


async def _assembly_product(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A product assembled from 1 part + 2 supplies. Returns
    (product_id, part_id, supply_id)."""
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
    part = await parts_service.create(
        session,
        name="Bracket",
        print_minutes=60,
        setup_minutes=0,
        parts_per_run=1,
        print_grams_by_material={m.id: Decimal("50")},
        actor_user_id=None,
    )
    await session.commit()
    supply = await supplies_service.create(
        session,
        name="M3 screw",
        unit="box",
        unit_cost=Decimal("10"),
        vendor=None,
        pieces_per_unit=100,  # $0.10/piece
        actor_user_id=None,
    )
    await session.commit()
    product = await products_service.create(
        session,
        name="Widget",
        description=None,
        unit_price=Decimal("25"),
        actor_user_id=None,
    )
    await session.commit()
    await bom_service.add_component(
        session,
        parent_product_id=product.id,
        component_kind="part",
        component_id=part.id,
        quantity=Decimal("1"),
        actor_user_id=None,
    )
    await bom_service.add_component(
        session,
        parent_product_id=product.id,
        component_kind="supply",
        component_id=supply.id,
        quantity=Decimal("2"),
        actor_user_id=None,
    )
    await session.commit()
    return product.id, part.id, supply.id


async def _seed_stock(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    location_id: uuid.UUID,
    quantity: Decimal,
    unit_cost: Decimal | None = None,
) -> None:
    await inventory_tx_service.record(
        session,
        kind="production_in",
        entity_kind=entity_kind,
        entity_id=entity_id,
        location_id=location_id,
        quantity=quantity,
        unit_cost=unit_cost,
        actor_user_id=None,
        reason="test seed",
    )
    await session.commit()


async def _on_hand(session: AsyncSession, entity_kind: str, entity_id: uuid.UUID) -> Decimal:
    rows = (
        await session.execute(
            select(InventoryOnHand.on_hand).where(
                InventoryOnHand.entity_kind == entity_kind,
                InventoryOnHand.entity_id == entity_id,
            )
        )
    ).all()
    return sum((r[0] for r in rows), Decimal("0"))


@pytest.mark.asyncio
async def test_build_consumes_components_and_credits_product(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    product_id, part_id, supply_id = await _assembly_product(app_session)
    # Seed enough for a build of 3 (3 parts, 6 supplies).
    await _seed_stock(
        app_session,
        entity_kind="part",
        entity_id=part_id,
        location_id=workshop_location.id,
        quantity=Decimal("5"),
    )
    await _seed_stock(
        app_session,
        entity_kind="supply",
        entity_id=supply_id,
        location_id=workshop_location.id,
        quantity=Decimal("20"),
    )

    create = await client.post(
        "/api/v1/builds",
        headers=_h(owner),
        json={"product_id": str(product_id), "quantity": 3},
    )
    assert create.status_code == 201, create.text
    build_id = create.json()["id"]
    assert create.json()["state"] == "draft"

    done = await client.post(f"/api/v1/builds/{build_id}/complete", headers=_h(owner))
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "completed"

    # Product credited by 3; part down to 5-3=2; supply down to 20-6=14.
    assert await _on_hand(app_session, "product", product_id) == Decimal("3")
    assert await _on_hand(app_session, "part", part_id) == Decimal("2")
    assert await _on_hand(app_session, "supply", supply_id) == Decimal("14")


@pytest.mark.asyncio
async def test_build_insufficient_stock_fails(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    product_id, part_id, supply_id = await _assembly_product(app_session)
    # Only 1 part on hand — a build of 2 needs 2 parts.
    await _seed_stock(
        app_session,
        entity_kind="part",
        entity_id=part_id,
        location_id=workshop_location.id,
        quantity=Decimal("1"),
    )
    await _seed_stock(
        app_session,
        entity_kind="supply",
        entity_id=supply_id,
        location_id=workshop_location.id,
        quantity=Decimal("100"),
    )

    create = await client.post(
        "/api/v1/builds",
        headers=_h(owner),
        json={"product_id": str(product_id), "quantity": 2},
    )
    build_id = create.json()["id"]
    done = await client.post(f"/api/v1/builds/{build_id}/complete", headers=_h(owner))
    assert done.status_code == 409, done.text

    # No partial consumption — stock unchanged, build still a draft.
    assert await _on_hand(app_session, "part", part_id) == Decimal("1")
    assert await _on_hand(app_session, "supply", supply_id) == Decimal("100")
    assert await _on_hand(app_session, "product", product_id) == Decimal("0")
    state = await client.get(f"/api/v1/builds/{build_id}", headers=_h(owner))
    assert state.json()["state"] == "draft"


@pytest.mark.asyncio
async def test_build_preview_reports_availability_and_cost(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    product_id, part_id, supply_id = await _assembly_product(app_session)
    await _seed_stock(
        app_session,
        entity_kind="part",
        entity_id=part_id,
        location_id=workshop_location.id,
        quantity=Decimal("1"),
    )
    # No supplies seeded → short.
    preview = await client.post(
        "/api/v1/builds/preview",
        headers=_h(owner),
        json={"product_id": str(product_id), "quantity": 1},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert len(body["lines"]) == 2
    assert body["can_build"] is False
    by_kind = {line["component_kind"]: line for line in body["lines"]}
    assert by_kind["part"]["sufficient"] is True
    assert by_kind["supply"]["sufficient"] is False
    # Component cost = part cost + 2 x supply per-piece ($0.10).
    # Part cost is rolled up from 50g x $0.02 = $1.00 material (+overhead etc).
    assert body["component_cost"] is not None


@pytest.mark.asyncio
async def test_build_cancel_makes_no_inventory_motion(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    product_id, part_id, _supply_id = await _assembly_product(app_session)
    create = await client.post(
        "/api/v1/builds",
        headers=_h(owner),
        json={"product_id": str(product_id), "quantity": 1},
    )
    build_id = create.json()["id"]
    cancelled = await client.post(f"/api/v1/builds/{build_id}/cancel", headers=_h(owner))
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"
    # Cannot complete a cancelled build.
    done = await client.post(f"/api/v1/builds/{build_id}/complete", headers=_h(owner))
    assert done.status_code == 409, done.text
    assert await _on_hand(app_session, "product", product_id) == Decimal("0")


@pytest.mark.asyncio
async def test_build_values_parts_at_fifo_lot_cost(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    """The product credited by a build is valued at the actual ledger lot
    cost of the parts it consumes + supplies + labor (#267 Phase 6a)."""
    from app.models.inventory_transaction import InventoryTransaction
    from sqlalchemy import and_

    owner = await _token(Role.OWNER, client, app_session)
    product_id, part_id, supply_id = await _assembly_product(app_session)
    # Part lot costed at $2.00/ea; supply per-piece = 10/100 = $0.10.
    await _seed_stock(
        app_session,
        entity_kind="part",
        entity_id=part_id,
        location_id=workshop_location.id,
        quantity=Decimal("5"),
        unit_cost=Decimal("2.00"),
    )
    await _seed_stock(
        app_session,
        entity_kind="supply",
        entity_id=supply_id,
        location_id=workshop_location.id,
        quantity=Decimal("20"),
        unit_cost=Decimal("0.10"),
    )

    create = await client.post(
        "/api/v1/builds",
        headers=_h(owner),
        json={"product_id": str(product_id), "quantity": 1},
    )
    build_id = create.json()["id"]
    done = await client.post(f"/api/v1/builds/{build_id}/complete", headers=_h(owner))
    assert done.status_code == 200, done.text
    body = done.json()
    # 1 part @ $2.00 + 2 supplies @ $0.10 = $2.20; assembly_minutes 0 → no labor.
    assert Decimal(body["unit_cost_cached"]) == Decimal("2.20")
    assert Decimal(body["total_cost_cached"]) == Decimal("2.20")

    # The product production_in row carries that unit cost.
    row = (
        await app_session.execute(
            select(InventoryTransaction).where(
                and_(
                    InventoryTransaction.entity_kind == "product",
                    InventoryTransaction.entity_id == product_id,
                    InventoryTransaction.kind == "production_in",
                    InventoryTransaction.linked_build_id == uuid.UUID(build_id),
                )
            )
        )
    ).scalar_one()
    assert Decimal(str(row.unit_cost_at_transaction)) == Decimal("2.20")


@pytest.mark.asyncio
async def test_job_completion_costs_the_part_lot(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    """A part-job credits part stock with a per-piece unit cost so the lot
    is costed for downstream FIFO (#267 Phase 6a)."""
    from app.models.inventory_transaction import InventoryTransaction
    from app.services import material_receipts as receipts_service

    owner = await _token(Role.OWNER, client, app_session)
    # Build a costed part: 50 g of $0.02/g filament → material cost in the
    # part recipe gives a non-zero per-piece cost.
    m = await materials_service.create(
        app_session,
        name=f"PLA {uuid.uuid4().hex[:6]}",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await app_session.commit()
    await receipts_service.record(
        app_session,
        material_id=m.id,
        grams=Decimal("1000"),
        total_cost=Decimal("20"),
        actor_user_id=None,
    )
    await app_session.commit()
    printer = await seed_printer(app_session)
    part = await parts_service.create(
        app_session,
        name="Bracket",
        print_minutes=60,
        setup_minutes=0,
        parts_per_run=1,
        print_grams_by_material={m.id: Decimal("50")},
        assigned_printer_ids=[printer.id],
        actor_user_id=None,
    )
    await app_session.commit()

    create = await client.post(
        "/api/v1/jobs",
        headers=_h(owner),
        json={"part_id": str(part.id), "quantity_ordered": 1},
    )
    job_id = create.json()["id"]
    plate_id = create.json()["plates"][0]["id"]
    await client.post(f"/api/v1/jobs/{job_id}/submit", headers=_h(owner))
    await client.post(f"/api/v1/jobs/{job_id}/start", headers=_h(owner))
    await client.post(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}/record-run",
        headers=_h(owner),
        json={"runs_completed_delta": 1},
    )
    await client.post(f"/api/v1/jobs/{job_id}/complete", headers=_h(owner))

    row = (
        await app_session.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.entity_kind == "part",
                InventoryTransaction.entity_id == part.id,
                InventoryTransaction.kind == "production_in",
            )
        )
    ).scalar_one()
    # Part lot carries a positive per-piece cost (>= the $1.00 material).
    assert row.unit_cost_at_transaction is not None
    assert Decimal(str(row.unit_cost_at_transaction)) >= Decimal("1.00")


@pytest.mark.asyncio
async def test_part_transactions_list_and_filter(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    """Part ledger rows serialize + filter via the read API (#267 Phase 6b)."""
    owner = await _token(Role.OWNER, client, app_session)
    _product_id, part_id, _supply_id = await _assembly_product(app_session)
    await _seed_stock(
        app_session,
        entity_kind="part",
        entity_id=part_id,
        location_id=workshop_location.id,
        quantity=Decimal("3"),
        unit_cost=Decimal("1.50"),
    )

    # List filtered to part — would 500 before the read-literal widening.
    listed = await client.get(
        "/api/v1/inventory/transactions",
        headers=_h(owner),
        params={"entity_kind": "part", "entity_id": str(part_id)},
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert any(i["entity_kind"] == "part" for i in items)

    # On-hand read endpoint accepts the part kind.
    oh = await client.get(
        "/api/v1/inventory/on-hand",
        headers=_h(owner),
        params={"entity_kind": "part", "entity_id": str(part_id)},
    )
    assert oh.status_code == 200, oh.text
    summaries = oh.json()["summaries"]
    assert summaries and Decimal(str(summaries[0]["total_on_hand"])) == Decimal("3")


@pytest.mark.asyncio
async def test_build_requires_existing_product(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/builds",
        headers=_h(owner),
        json={"product_id": str(uuid.uuid4()), "quantity": 1},
    )
    assert r.status_code == 400, r.text
