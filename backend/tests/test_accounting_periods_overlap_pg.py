"""GiST exclusion constraint rejects overlapping periods (Phase 4.3, #66).

PG-only integration: relies on the ``btree_gist`` extension and the
``daterange`` GiST exclusion installed by ``0019_accounting_periods``.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.models import Base
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def pg_factory(postgres_url: str):
    eng = create_async_engine(postgres_url, future=True)
    async with eng.begin() as conn:
        # btree_gist + GiST exclusion are the PG-only DDL we mirror here
        # (Base.metadata.create_all doesn't emit either by itself).
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "ALTER TABLE accounting_period ADD CONSTRAINT "
                "ex_accounting_period_no_overlap EXCLUDE USING gist ("
                "daterange(start_date, end_date, '[]') WITH &&)"
            )
        )
    factory = async_sessionmaker(eng, expire_on_commit=False)
    yield factory
    await eng.dispose()


@pytest.mark.asyncio
async def test_db_rejects_overlap(pg_factory) -> None:
    factory = pg_factory
    async with factory() as s:
        await s.execute(
            text(
                "INSERT INTO accounting_period "
                "(id, name, start_date, end_date, state, created_at, updated_at) "
                "VALUES (:id, 'a', '2026-01-01', '2026-03-31', 'open', now(), now())"
            ),
            {"id": uuid.uuid4()},
        )
        await s.commit()

    async with factory() as s:
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO accounting_period "
                    "(id, name, start_date, end_date, state, created_at, updated_at) "
                    "VALUES (:id, 'b', '2026-02-01', '2026-04-30', 'open', now(), now())"
                ),
                {"id": uuid.uuid4()},
            )
            await s.commit()
