"""Postgres integration test: the partial unique index
``ux_inventory_location_code_active`` rejects two active rows with the
same code at the DB level, while allowing archived rows to share codes.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.models import Base
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def pg_engine(postgres_url: str):
    eng = create_async_engine(postgres_url, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def pg_session_factory(pg_engine):
    return async_sessionmaker(pg_engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_two_active_same_code_rejected_by_db(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        s.add(
            InventoryLocation(
                id=uuid.uuid4(),
                name="One",
                code="WSB",
                kind=InventoryLocationKind.WORKSHOP,
                is_archived=False,
            )
        )
        await s.commit()

    async with pg_session_factory() as s:
        s.add(
            InventoryLocation(
                id=uuid.uuid4(),
                name="Two",
                code="WSB",
                kind=InventoryLocationKind.STAGING,
                is_archived=False,
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_two_archived_same_code_allowed(pg_session_factory) -> None:
    """Partial index excludes archived rows; two archived may share a code."""
    async with pg_session_factory() as s:
        s.add_all(
            [
                InventoryLocation(
                    id=uuid.uuid4(),
                    name="Old A",
                    code="FG",
                    kind=InventoryLocationKind.FINISHED_GOODS,
                    is_archived=True,
                ),
                InventoryLocation(
                    id=uuid.uuid4(),
                    name="Old B",
                    code="FG",
                    kind=InventoryLocationKind.FINISHED_GOODS,
                    is_archived=True,
                ),
                InventoryLocation(
                    id=uuid.uuid4(),
                    name="Current FG",
                    code="FG",
                    kind=InventoryLocationKind.FINISHED_GOODS,
                    is_archived=False,
                ),
            ]
        )
        await s.commit()
