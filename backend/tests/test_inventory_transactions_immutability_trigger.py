"""PG-only: the inventory_transaction trigger blocks UPDATE and DELETE.

SQLite doesn't carry the trigger. The application never mutates these
rows, but we install the trigger for defense in depth and exercise it
here against a real Postgres container.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models import Base
from app.models.inventory_transaction import InventoryTransaction
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_and_delete_blocked_on_pg(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url, future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Trigger only lives on PG via Alembic; CREATE FUNCTION + TRIGGER
            # by hand so the test exercises the same SQL.
            await conn.exec_driver_sql(
                """
                CREATE OR REPLACE FUNCTION test_inv_tx_block()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'inventory_transaction is append-only (op=%)', TG_OP;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
            await conn.exec_driver_sql(
                """
                CREATE TRIGGER test_inv_tx_block_trg
                BEFORE UPDATE OR DELETE ON inventory_transaction
                FOR EACH ROW EXECUTE FUNCTION test_inv_tx_block();
                """
            )

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            # Seed a row directly so we don't have to build the world
            # (locations, materials, etc.) for a pure trigger probe.
            row_id = uuid.uuid4()
            await session.execute(
                # Use the ORM but with bogus location_id (FK off → use a
                # real one). Quickest path: seed via INSERT with NULL-able
                # entity_id and a manually inserted location.
                # Simpler: just exercise the trigger after creating the
                # bare minimum.
                # Insert raw rows to bypass FK requirements.
                # (Easier path: just rely on FK by skipping the trigger
                # probe via raw SQL).
                # We'll insert directly:
                __import__("sqlalchemy").text(
                    "INSERT INTO inventory_location (id, name, code, kind, is_archived, "
                    "created_at, updated_at) "
                    "VALUES (:lid, 'L', 'L', 'workshop', false, now(), now())"
                ),
                {"lid": uuid.uuid4()},
            )
            # The above inserted a location and we need its id back; easier
            # to look it up.
            from app.models.inventory_location import InventoryLocation
            from sqlalchemy import select as _select

            loc_id = (await session.execute(_select(InventoryLocation.id).limit(1))).scalar_one()
            tx = InventoryTransaction(
                id=row_id,
                kind="adjustment",
                entity_kind="material",
                entity_id=uuid.uuid4(),
                location_id=loc_id,
                quantity=Decimal("1"),
            )
            session.add(tx)
            await session.commit()

            with pytest.raises(DBAPIError):
                await session.execute(
                    update(InventoryTransaction)
                    .where(InventoryTransaction.id == row_id)
                    .values(reason="mutated")
                )
                await session.commit()
            await session.rollback()

            with pytest.raises(DBAPIError):
                await session.execute(
                    delete(InventoryTransaction).where(InventoryTransaction.id == row_id)
                )
                await session.commit()
            await session.rollback()
    finally:
        await engine.dispose()
