"""BOM supplies flow into a job's cost (per-finished-piece).

Covers the wiring that makes a product-linked job's Live cost include the
non-printed parts from the product's BOM (screws, magnets, packaging),
costed per piece (``unit_cost / pieces_per_unit``) and scaled by the
number of pieces produced. See ``app.services.bom.supply_line_costs_per_piece``
and ``CostEngineService``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services import bom as bom_service
from app.services import supplies as supplies_service
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_product, token_for


@pytest.mark.asyncio
async def test_supply_line_costs_per_piece_uses_pieces_per_unit(
    app_session: AsyncSession,
) -> None:
    """A box of 100 screws @ $10, 4 per product → $0.40 per piece."""
    product = await seed_product(app_session, name="Boxed")
    supply = await supplies_service.create(
        app_session,
        name="Screws",
        unit="box",
        unit_cost=Decimal("10"),
        vendor=None,
        actor_user_id=None,
        pieces_per_unit=100,
    )
    await app_session.commit()
    await bom_service.add_component(
        app_session,
        parent_product_id=product.id,
        component_kind="supply",
        component_id=supply.id,
        quantity=Decimal("4"),
        actor_user_id=None,
    )
    await app_session.commit()

    lines = await bom_service.supply_line_costs_per_piece(app_session, product_id=product.id)
    # 4 pieces * ($10 / 100) = $0.40
    assert lines == {supply.id: Decimal("0.400000")}


@pytest.mark.asyncio
async def test_supply_line_costs_falls_back_to_unit_cost_when_no_pieces_per_unit(
    app_session: AsyncSession,
) -> None:
    product = await seed_product(app_session, name="Unboxed")
    supply = await supplies_service.create(
        app_session,
        name="Magnet",
        unit="ea",
        unit_cost=Decimal("0.50"),
        vendor=None,
        actor_user_id=None,
    )
    await app_session.commit()
    await bom_service.add_component(
        app_session,
        parent_product_id=product.id,
        component_kind="supply",
        component_id=supply.id,
        quantity=Decimal("2"),
        actor_user_id=None,
    )
    await app_session.commit()

    lines = await bom_service.supply_line_costs_per_piece(app_session, product_id=product.id)
    # No pieces_per_unit → 1 unit = 1 piece → 2 * $0.50 = $1.00
    assert lines == {supply.id: Decimal("1.000000")}


@pytest.mark.asyncio
async def test_job_cost_includes_bom_supplies_scaled_by_pieces(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """End-to-end: product BOM supply shows up in the job's supply_cost,
    scaled by pieces produced."""
    product = await seed_product(app_session, name="Assembled")
    supply = await supplies_service.create(
        app_session,
        name="Insert",
        unit="box",
        unit_cost=Decimal("10"),
        vendor=None,
        actor_user_id=None,
        pieces_per_unit=100,  # → $0.10 / piece
    )
    await app_session.commit()
    await bom_service.add_component(
        app_session,
        parent_product_id=product.id,
        component_kind="supply",
        component_id=supply.id,
        quantity=Decimal("4"),  # 4 inserts/piece → $0.40 / piece
        actor_user_id=None,
    )
    await app_session.commit()

    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={
            "product_id": str(product.id),
            "quantity_ordered": 3,
            "priority": 0,
            "plates": [
                {
                    "name": "Plate A",
                    "plate_number": 1,
                    "parts_per_set": 1,
                    "print_minutes": 60,
                    "print_grams_by_material": {},
                    "print_hours_setup_minutes": 0,
                    "assigned_printer_ids": [],
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]

    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 3 ordered / 1 per set = 3 pieces. $0.40/piece * 3 = $1.20.
    assert body["sets_required"] == 3
    assert Decimal(body["supply_cost"]) == Decimal("1.20")


@pytest.mark.asyncio
async def test_inputs_path_with_product_id_includes_bom_supplies(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """The composer's draft path (inputs + product_id) folds in the
    product's BOM supplies before any job is saved."""
    product = await seed_product(app_session, name="Drafted")
    supply = await supplies_service.create(
        app_session,
        name="Clip",
        unit="box",
        unit_cost=Decimal("10"),
        vendor=None,
        actor_user_id=None,
        pieces_per_unit=100,  # → $0.10 / piece
    )
    await app_session.commit()
    await bom_service.add_component(
        app_session,
        parent_product_id=product.id,
        component_kind="supply",
        component_id=supply.id,
        quantity=Decimal("4"),  # $0.40 / piece
        actor_user_id=None,
    )
    await app_session.commit()

    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(owner),
        json={
            "product_id": str(product.id),
            "inputs": {
                "plates": [
                    {
                        "parts_per_set": 1,
                        "print_minutes": 60,
                        "print_grams_by_material": {},
                        "setup_minutes": 0,
                        "assigned_printer_ids": [],
                    }
                ],
                "quantity_ordered": 3,
            },
        },
    )
    assert r.status_code == 200, r.text
    # Same shape as the saved-job case: $0.40/piece * 3 = $1.20.
    assert Decimal(r.json()["supply_cost"]) == Decimal("1.20")


@pytest.mark.asyncio
async def test_product_id_without_inputs_is_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """product_id alongside job_id (or alone) is ambiguous → 422."""
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(owner),
        json={"product_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_product_without_bom_has_zero_supply_cost(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """No BOM supplies → supply_cost stays zero (no regression)."""
    product = await seed_product(app_session, name="Bare")
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={
            "product_id": str(product.id),
            "quantity_ordered": 2,
            "priority": 0,
            "plates": [
                {
                    "name": "Plate A",
                    "plate_number": 1,
                    "parts_per_set": 1,
                    "print_minutes": 30,
                    "print_grams_by_material": {},
                    "print_hours_setup_minutes": 0,
                    "assigned_printer_ids": [],
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(owner),
        json={"job_id": create.json()["id"]},
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["supply_cost"]) == Decimal("0.00")
