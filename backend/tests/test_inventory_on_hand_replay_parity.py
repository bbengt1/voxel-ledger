"""Phase 3.3 (#52) inventory_on_hand replay parity.

Drives N TransactionRecorded events across mixed entities, locations,
and kinds, snapshots the read-model, truncates it, replays from
position=0, and asserts the rebuilt table matches the snapshot exactly.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.inventory_on_hand import InventoryOnHand
from app.models.projection import ProjectionCursor
from app.projections import registry as projection_registry
from app.projections.inventory_on_hand import HANDLER_NAME
from app.projections.replay import replay_handler
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as transactions_service
from app.services import materials as materials_service
from app.services import supplies as supplies_service
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_inventory_on_hand_replay_parity(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as s:
        loc_ws = await locations_service.create(
            s, name="Workshop", code="WS", kind="workshop", actor_user_id=None
        )
        loc_fg = await locations_service.create(
            s, name="Finished Goods", code="FG", kind="finished_goods", actor_user_id=None
        )
        mat = await materials_service.create(
            s,
            name="PLA",
            brand="X",
            material_type="PLA",
            color=None,
            density_g_per_cm3=None,
            spool_weight_grams=Decimal("1000"),
            actor_user_id=None,
        )
        sup = await supplies_service.create(
            s,
            name="Bag",
            unit="ea",
            unit_cost=Decimal("0.10"),
            vendor=None,
            actor_user_id=None,
        )
        await s.commit()

    movements = [
        ("production_in", "material", mat.id, loc_ws.id, Decimal("100")),
        ("sale_out", "material", mat.id, loc_ws.id, Decimal("25")),
        ("adjustment", "supply", sup.id, loc_ws.id, Decimal("50")),
        ("waste", "supply", sup.id, loc_ws.id, Decimal("5")),
        ("production_in", "material", mat.id, loc_fg.id, Decimal("30")),
    ]
    async with factory() as s:
        for kind, ek, eid, lid, q in movements:
            await transactions_service.record(
                s,
                kind=kind,
                entity_kind=ek,
                entity_id=eid,
                location_id=lid,
                quantity=q,
                actor_user_id=None,
            )
        # And one transfer (two events, two rows).
        await transactions_service.record_transfer(
            s,
            entity_kind="material",
            entity_id=mat.id,
            from_location_id=loc_ws.id,
            to_location_id=loc_fg.id,
            quantity=Decimal("10"),
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        rows = (
            (
                await s.execute(
                    select(InventoryOnHand).order_by(
                        InventoryOnHand.entity_kind,
                        InventoryOnHand.entity_id,
                        InventoryOnHand.location_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        before = {(r.entity_kind, r.entity_id, r.location_id): r.on_hand for r in rows}
    assert before  # there should be data

    # Truncate + reset cursor.
    async with factory() as s:
        await s.execute(delete(InventoryOnHand))
        await s.execute(
            delete(ProjectionCursor).where(ProjectionCursor.handler_name == HANDLER_NAME)
        )
        await s.commit()

    handler = projection_registry.get_handler(HANDLER_NAME)
    await replay_handler(handler, factory, from_position=0)

    async with factory() as s:
        rows = (
            (
                await s.execute(
                    select(InventoryOnHand).order_by(
                        InventoryOnHand.entity_kind,
                        InventoryOnHand.entity_id,
                        InventoryOnHand.location_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        after = {(r.entity_kind, r.entity_id, r.location_id): r.on_hand for r in rows}

    assert after == before
