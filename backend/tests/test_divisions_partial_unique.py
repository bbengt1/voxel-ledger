"""Postgres integration test for the partial unique index on
``division(code) WHERE is_archived = false`` (Phase 4.5).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.models import Base
from app.models.division import Division
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
        s.add(Division(id=uuid.uuid4(), name="A", code="3DP", is_archived=False))
        await s.commit()

    async with pg_session_factory() as s:
        s.add(Division(id=uuid.uuid4(), name="B", code="3DP", is_archived=False))
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_two_archived_same_code_allowed(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        s.add_all(
            [
                Division(id=uuid.uuid4(), name="Old", code="OLD", is_archived=True),
                Division(id=uuid.uuid4(), name="Older", code="OLD", is_archived=True),
                Division(id=uuid.uuid4(), name="Now", code="OLD", is_archived=False),
            ]
        )
        await s.commit()
