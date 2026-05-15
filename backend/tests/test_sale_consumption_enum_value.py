"""``sale_consumption`` inventory-transaction-kind enum value (Phase 6.3, #95).

Asserts the model + ORM accept the new enum value and that the
ledger service round-trips a ``sale_consumption`` row end-to-end. The
migration's PG ``ALTER TYPE`` path is exercised in CI via the
postgres_url fixture; on the default SQLite test driver the
``batch_alter_table`` path keeps the CHECK constraint in sync.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.inventory_transaction import (
    INVENTORY_TRANSACTION_KIND_VALUES,
    KIND_PRODUCTION_IN,
    KIND_SALE_CONSUMPTION,
    InventoryTransaction,
)
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as inventory_tx_service
from app.services import products as products_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def test_sale_consumption_in_kind_values():
    assert "sale_consumption" in INVENTORY_TRANSACTION_KIND_VALUES
    assert KIND_SALE_CONSUMPTION == "sale_consumption"


@pytest.mark.asyncio
async def test_orm_persists_sale_consumption_row(session: AsyncSession, engine) -> None:
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    location = await locations_service.create(
        session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )
    product = await products_service.create(
        session,
        name="Widget",
        description=None,
        unit_price=Decimal("20.00"),
        sku=f"PRD-{uuid.uuid4().hex[:6]}",
        actor_user_id=None,
    )
    await inventory_tx_service.record(
        session,
        kind=KIND_PRODUCTION_IN,
        entity_kind="product",
        entity_id=product.id,
        location_id=location.id,
        quantity=Decimal("5"),
        unit_cost=Decimal("2.00"),
        actor_user_id=None,
    )
    tx = await inventory_tx_service.record(
        session,
        kind=KIND_SALE_CONSUMPTION,
        entity_kind="product",
        entity_id=product.id,
        location_id=location.id,
        quantity=Decimal("2"),
        unit_cost=Decimal("2.00"),
        actor_user_id=None,
    )
    assert tx.kind == KIND_SALE_CONSUMPTION
    # Sign convention: sale_consumption is a NEGATIVE kind.
    assert tx.quantity == Decimal("-2.000000")

    # Round-trip from the DB.
    refreshed = (
        await session.execute(select(InventoryTransaction).where(InventoryTransaction.id == tx.id))
    ).scalar_one()
    assert refreshed.kind == "sale_consumption"
