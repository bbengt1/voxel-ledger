"""BOM events surface in the audit log via the wildcard projection."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.events.types import catalog as catalog_events
from app.models import Base
from app.models.audit import AuditLog
from app.services import bom as bom_service
from app.services import products as products_service
from app.services import supplies as supplies_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_bom_events_appear_in_audit_log(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as s:
        p = await products_service.create(
            s, name="P", description=None, unit_price=Decimal("1"), actor_user_id=None
        )
        sup = await supplies_service.create(
            s,
            name="bag",
            unit="ea",
            unit_cost=Decimal("3"),
            vendor=None,
            on_hand=Decimal("0"),
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        item = await bom_service.add_component(
            s,
            parent_product_id=p.id,
            component_kind="supply",
            component_id=sup.id,
            quantity=Decimal("2"),
            actor_user_id=None,
        )
        await bom_service.update_component_quantity(
            s,
            bom_item_id=item.id,
            new_quantity=Decimal("4"),
            actor_user_id=None,
        )
        await bom_service.remove_component(
            s,
            bom_item_id=item.id,
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        rows = (await s.execute(select(AuditLog.event_type))).all()
        types = {r[0] for r in rows}
        assert catalog_events.TYPE_BOM_COMPONENT_ADDED in types
        assert catalog_events.TYPE_BOM_COMPONENT_QUANTITY_CHANGED in types
        assert catalog_events.TYPE_BOM_COMPONENT_REMOVED in types
        assert catalog_events.TYPE_PRODUCT_COST_CHANGED in types
