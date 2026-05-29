"""Refactored material receipt emits BOTH inventory.MaterialReceived AND
inventory.TransactionRecorded, and writes a row to both tables."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.event import Event
from app.models.inventory_transaction import InventoryTransaction
from app.models.material_receipt import MaterialReceipt
from app.services import inventory_locations as locations_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_receipt_creates_both_rows_and_emits_both_events(
    session: AsyncSession, engine
) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    loc = await locations_service.create(
        session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )
    mat = await materials_service.create(
        session,
        name="PLA",
        brand="A",
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )

    await receipts_service.record(
        session,
        material_id=mat.id,
        grams=Decimal("1000"),
        total_cost=Decimal("20.00"),
        vendor="ACME",
        reference="INV-42",
        actor_user_id=None,
    )
    await session.commit()

    receipts = (
        (
            await session.execute(
                select(MaterialReceipt).where(MaterialReceipt.material_id == mat.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(receipts) == 1

    tx_rows = (await session.execute(select(InventoryTransaction))).scalars().all()
    assert len(tx_rows) == 1
    assert tx_rows[0].kind == "receipt"
    assert tx_rows[0].entity_kind == "material"
    assert tx_rows[0].entity_id == mat.id
    assert tx_rows[0].location_id == loc.id
    assert tx_rows[0].quantity == Decimal("1000")
    assert tx_rows[0].unit_cost_at_transaction == Decimal("0.020000")

    event_types = [
        e.type
        for e in (await session.execute(select(Event).order_by(Event.position))).scalars().all()
    ]
    # Both classes of event must be present from the same receipt call.
    assert "inventory.MaterialReceived" in event_types
    assert "inventory.TransactionRecorded" in event_types
