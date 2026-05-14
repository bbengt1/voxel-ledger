"""MaterialReceiptsService: happy path + validation rejections."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.event import Event
from app.models.material_receipt import MaterialReceipt
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_material(session):
    m = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        actor_user_id=None,
    )
    return m


@pytest.mark.asyncio
async def test_record_receipt_happy_path(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    m = await _seed_material(session)
    receipt = await receipts_service.record(
        session,
        material_id=m.id,
        grams=Decimal("1000"),
        total_cost=Decimal("20.00"),
        vendor="ACME",
        reference="INV-1",
        notes="bulk order",
        actor_user_id=None,
    )
    await session.commit()

    assert receipt.grams == Decimal("1000")
    assert receipt.total_cost == Decimal("20.00")
    assert receipt.unit_cost_at_receipt == Decimal("0.020000")

    rows = (
        (await session.execute(select(MaterialReceipt).where(MaterialReceipt.material_id == m.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1

    events = (
        (await session.execute(select(Event).where(Event.type == "inventory.MaterialReceived")))
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["material_id"] == str(m.id)
    assert payload["grams"] == "1000"
    assert payload["total_cost"] == "20.00"
    assert payload["unit_cost_at_receipt"] == "0.020000"


@pytest.mark.asyncio
async def test_record_rejects_non_positive_grams(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    m = await _seed_material(session)
    with pytest.raises(receipts_service.InvalidGramsError):
        await receipts_service.record(
            session,
            material_id=m.id,
            grams=Decimal("0"),
            total_cost=Decimal("1.00"),
            actor_user_id=None,
        )
    with pytest.raises(receipts_service.InvalidGramsError):
        await receipts_service.record(
            session,
            material_id=m.id,
            grams=Decimal("-1"),
            total_cost=Decimal("1.00"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_record_rejects_negative_total_cost(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    m = await _seed_material(session)
    with pytest.raises(receipts_service.InvalidTotalCostError):
        await receipts_service.record(
            session,
            material_id=m.id,
            grams=Decimal("100"),
            total_cost=Decimal("-0.01"),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_record_zero_total_cost_allowed(session: AsyncSession, engine) -> None:
    """Free samples / promo material — cost may be zero."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    m = await _seed_material(session)
    r = await receipts_service.record(
        session,
        material_id=m.id,
        grams=Decimal("500"),
        total_cost=Decimal("0"),
        actor_user_id=None,
    )
    assert r.unit_cost_at_receipt == Decimal("0.000000")


@pytest.mark.asyncio
async def test_list_for_material_pagination(session: AsyncSession, engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    m = await _seed_material(session)
    for _ in range(3):
        await receipts_service.record(
            session,
            material_id=m.id,
            grams=Decimal("100"),
            total_cost=Decimal("5.00"),
            actor_user_id=None,
        )
    page = await receipts_service.list_for_material(session, material_id=m.id, limit=2)
    assert len(page.items) == 2
    assert page.next_cursor is not None
    page2 = await receipts_service.list_for_material(
        session, material_id=m.id, limit=2, cursor=page.next_cursor
    )
    assert len(page2.items) == 1
