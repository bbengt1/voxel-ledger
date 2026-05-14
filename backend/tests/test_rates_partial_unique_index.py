"""Postgres integration test: the partial unique index
``ux_rate_default_per_kind`` rejects two default rates of the same kind
at the DB level (not just app-level).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.rate import Rate, RateKind
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
async def test_two_defaults_same_kind_rejected_by_db(pg_session_factory) -> None:
    async with pg_session_factory() as s:
        s.add(
            Rate(
                id=uuid.uuid4(),
                name="Labor A",
                kind=RateKind.LABOR,
                value=Decimal("25"),
                is_default_for_kind=True,
            )
        )
        await s.commit()

    async with pg_session_factory() as s:
        s.add(
            Rate(
                id=uuid.uuid4(),
                name="Labor B",
                kind=RateKind.LABOR,
                value=Decimal("30"),
                is_default_for_kind=True,
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_two_defaults_different_kinds_allowed(pg_session_factory) -> None:
    """Different kinds can each have their own default row simultaneously."""
    async with pg_session_factory() as s:
        s.add_all(
            [
                Rate(
                    id=uuid.uuid4(),
                    name="Labor default",
                    kind=RateKind.LABOR,
                    value=Decimal("25"),
                    is_default_for_kind=True,
                ),
                Rate(
                    id=uuid.uuid4(),
                    name="Machine default",
                    kind=RateKind.MACHINE,
                    value=Decimal("5"),
                    is_default_for_kind=True,
                ),
                Rate(
                    id=uuid.uuid4(),
                    name="Overhead default",
                    kind=RateKind.OVERHEAD,
                    value=Decimal("0.15"),
                    is_default_for_kind=True,
                ),
            ]
        )
        await s.commit()
