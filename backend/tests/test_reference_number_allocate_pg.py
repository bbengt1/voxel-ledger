"""Concurrent allocator property test against real Postgres.

Headline acceptance test: 100 concurrent ``allocate("S")`` calls across
independent sessions must yield 100 unique references that span exactly
the contiguous range 1..100. No duplicates, no gaps, no lost updates.

SQLite serializes its writers under a global write lock so it can't
demonstrate this property — only PG (where rows are independently
lockable) can.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.models import Base
from app.services.reference_number import ReferenceNumberService, parse_reference
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
async def test_pg_sequential_allocation(pg_session_factory) -> None:
    year = datetime.now(UTC).year
    async with pg_session_factory() as s:
        first = await ReferenceNumberService.allocate("S", session=s)
        second = await ReferenceNumberService.allocate("S", session=s)
        await s.commit()
    assert first == f"S-{year}-0001"
    assert second == f"S-{year}-0002"


@pytest.mark.asyncio
async def test_pg_concurrent_allocations_are_unique_and_contiguous(
    pg_session_factory,
) -> None:
    """Spawn N concurrent allocations across independent sessions and
    assert the results are exactly the set 1..N with no duplicates."""
    n = 100

    async def one_alloc() -> str:
        async with pg_session_factory() as s:
            ref = await ReferenceNumberService.allocate("S", session=s, year=2026)
            await s.commit()
            return ref

    results = await asyncio.gather(*(one_alloc() for _ in range(n)))

    assert len(set(results)) == n, "duplicate references issued under concurrency"
    values = sorted(parse_reference(r)[2] for r in results)
    assert values == list(range(1, n + 1)), values
    # All in the same (prefix, year) bucket.
    for r in results:
        prefix, year, _ = parse_reference(r)
        assert prefix == "S"
        assert year == 2026


@pytest.mark.asyncio
async def test_pg_concurrent_allocations_across_prefixes(
    pg_session_factory,
) -> None:
    """Sanity: two different prefixes don't interfere even under heavy
    concurrent load; each bucket gets a contiguous 1..N range."""
    n = 25

    async def alloc(prefix: str) -> str:
        async with pg_session_factory() as s:
            ref = await ReferenceNumberService.allocate(prefix, session=s, year=2026)
            await s.commit()
            return ref

    tasks = [alloc("S") for _ in range(n)] + [alloc("INV") for _ in range(n)]
    results = await asyncio.gather(*tasks)

    by_prefix: dict[str, list[int]] = {"S": [], "INV": []}
    for r in results:
        p, _, v = parse_reference(r)
        by_prefix[p].append(v)
    for prefix, vals in by_prefix.items():
        assert sorted(vals) == list(range(1, n + 1)), (prefix, vals)
