"""Partial-unique-index behavior for ``product.upc``.

NULL UPCs must coexist freely; non-NULL UPCs must be unique. The
constraint is enforced by a partial unique index. Verified against real
Postgres so the partial-unique semantics actually run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.services import products as products_service
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upc_partial_unique_on_postgres(postgres_url: str) -> None:
    engine = create_async_engine(postgres_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Mirror the PG-only DDL the 0003 migration adds so the
        # event-store append path works here too.
        await conn.execute(
            text("CREATE SEQUENCE IF NOT EXISTS event_position_seq OWNED BY event.position")
        )
        await conn.execute(
            text(
                "ALTER TABLE event ALTER COLUMN position SET DEFAULT nextval('event_position_seq')"
            )
        )

    # Multiple NULL UPCs are allowed.
    async with factory() as session:
        for i in range(3):
            await products_service.create(
                session,
                name=f"N{i}",
                description=None,
                unit_price=Decimal("1.00"),
                sku=f"NULL-{i}",
                upc=None,
                actor_user_id=None,
            )
        await session.commit()

    # First non-NULL UPC succeeds.
    async with factory() as session:
        await products_service.create(
            session,
            name="UPC One",
            description=None,
            unit_price=Decimal("1.00"),
            sku="WITH-UPC-1",
            upc="012345678905",
            actor_user_id=None,
        )
        await session.commit()

    # Duplicate non-NULL UPC raises. Service-level check catches it first;
    # the partial unique index is a belt-and-suspenders backstop.
    async with factory() as session:
        with pytest.raises((products_service.DuplicateUpcError, IntegrityError)):
            await products_service.create(
                session,
                name="UPC Two",
                description=None,
                unit_price=Decimal("1.00"),
                sku="WITH-UPC-2",
                upc="012345678905",
                actor_user_id=None,
            )
            await session.commit()

    await engine.dispose()
