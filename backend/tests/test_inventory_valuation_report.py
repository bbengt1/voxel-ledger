"""Inventory valuation report tests (Phase 10.5, #180)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.models.inventory_on_hand import InventoryOnHand
from app.models.material import Material
from app.models.supply import Supply
from app.services.reports import inventory_valuation as report_service
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_location(session: AsyncSession, *, code: str, name: str) -> InventoryLocation:
    loc = InventoryLocation(
        id=uuid.uuid4(),
        code=code,
        name=name,
        kind=InventoryLocationKind.WORKSHOP,
        is_archived=False,
    )
    session.add(loc)
    await session.flush()
    return loc


async def _seed_material(session: AsyncSession, *, name: str, cost_per_gram: str) -> Material:
    mat = Material(
        id=uuid.uuid4(),
        name=name,
        material_type="PLA",
        current_cost_per_gram=Decimal(cost_per_gram),
    )
    session.add(mat)
    await session.flush()
    return mat


async def _seed_supply(session: AsyncSession, *, name: str, unit_cost: str) -> Supply:
    sup = Supply(
        id=uuid.uuid4(),
        name=name,
        unit="ea",
        unit_cost=Decimal(unit_cost),
    )
    session.add(sup)
    await session.flush()
    return sup


async def _seed_on_hand(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    location_id: uuid.UUID,
    on_hand: str,
) -> InventoryOnHand:
    row = InventoryOnHand(
        id=uuid.uuid4(),
        entity_kind=entity_kind,
        entity_id=entity_id,
        location_id=location_id,
        on_hand=Decimal(on_hand),
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_uses_weighted_avg_cost(client: AsyncClient, app_session: AsyncSession) -> None:
    loc = await _seed_location(app_session, code="WS-A", name="Workshop A")
    mat = await _seed_material(app_session, name="PLA", cost_per_gram="0.04")
    sup = await _seed_supply(app_session, name="Bags", unit_cost="0.50")
    await _seed_on_hand(
        app_session,
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        on_hand="500",
    )
    await _seed_on_hand(
        app_session,
        entity_kind="supply",
        entity_id=sup.id,
        location_id=loc.id,
        on_hand="100",
    )
    await app_session.commit()

    report = await report_service.build(app_session)
    # Material: 500 g * $0.04 = $20. Supply: 100 * $0.50 = $50. Total = $70.
    assert report.total_valuation == Decimal("70.00")
    assert report.totals_by_kind == {"material": Decimal("20.00"), "supply": Decimal("50.00")}
    assert report.totals_by_location[str(loc.id)] == Decimal("70.00")


@pytest.mark.asyncio
async def test_includes_part_valuation(client: AsyncClient, app_session: AsyncSession) -> None:
    """Parts contribute their cached cost to inventory value (#267 Phase 6a)."""
    from app.models.part import Part

    loc = await _seed_location(app_session, code="WS-P", name="Workshop P")
    part = Part(
        id=uuid.uuid4(),
        sku="P-1",
        name="Bracket",
        parts_per_run=1,
        unit_cost_cached=Decimal("1.50"),
    )
    app_session.add(part)
    await app_session.flush()
    await _seed_on_hand(
        app_session,
        entity_kind="part",
        entity_id=part.id,
        location_id=loc.id,
        on_hand="4",
    )
    await app_session.commit()

    report = await report_service.build(app_session)
    # 4 parts * $1.50 = $6.00.
    assert report.totals_by_kind.get("part") == Decimal("6.00")
    assert report.total_valuation == Decimal("6.00")
    part_rows = [r for r in report.rows if r.entity_kind == "part"]
    assert len(part_rows) == 1
    assert part_rows[0].name == "Bracket"
    assert part_rows[0].sku == "P-1"


@pytest.mark.asyncio
async def test_location_filter(client: AsyncClient, app_session: AsyncSession) -> None:
    loc_a = await _seed_location(app_session, code="WS-A", name="Workshop A")
    loc_b = await _seed_location(app_session, code="WS-B", name="Workshop B")
    mat = await _seed_material(app_session, name="PLA", cost_per_gram="0.04")
    await _seed_on_hand(
        app_session,
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc_a.id,
        on_hand="100",
    )
    await _seed_on_hand(
        app_session,
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc_b.id,
        on_hand="200",
    )
    await app_session.commit()

    full = await report_service.build(app_session)
    assert full.total_valuation == Decimal("12.00")  # 300 * 0.04

    only_a = await report_service.build(app_session, location_id=loc_a.id)
    assert only_a.total_valuation == Decimal("4.00")  # 100 * 0.04


@pytest.mark.asyncio
async def test_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
    loc = await _seed_location(app_session, code="WS-A", name="Workshop A")
    mat = await _seed_material(app_session, name="PLA", cost_per_gram="0.04")
    await _seed_on_hand(
        app_session,
        entity_kind="material",
        entity_id=mat.id,
        location_id=loc.id,
        on_hand="500",
    )
    await app_session.commit()

    report = await report_service.build(app_session)
    csv = report_service.to_csv(report)
    rows = csv.strip().splitlines()
    assert rows[0].split(",") == [
        "location",
        "entity_kind",
        "sku",
        "name",
        "on_hand",
        "unit_cost",
        "valuation",
    ]
    assert any(line.startswith("GRAND TOTAL,") for line in rows)
