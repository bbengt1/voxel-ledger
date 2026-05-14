"""Sequential allocator happy-path tests against SQLite.

SQLite serializes its writers under a global lock so it can't prove
concurrent correctness — that's what the PG integration test is for —
but it's plenty for confirming the sequence-of-one-by-one allocations,
the year-default behavior, and the multi-prefix isolation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest
from app.models import Base
from app.services import reference_number as rn
from app.services.reference_number import ReferenceNumberService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def _reset_overflow_log_cache() -> None:
    rn._PADDING_OVERFLOW_LOGGED.clear()
    rn.PADDING_OVERRIDES.clear()
    yield
    rn._PADDING_OVERFLOW_LOGGED.clear()
    rn.PADDING_OVERRIDES.clear()


@pytest.mark.asyncio
async def test_sequential_allocations_increment(session: AsyncSession) -> None:
    year = datetime.now(UTC).year
    out = [await ReferenceNumberService.allocate("S", session=session) for _ in range(5)]
    await session.commit()
    assert out == [
        f"S-{year}-0001",
        f"S-{year}-0002",
        f"S-{year}-0003",
        f"S-{year}-0004",
        f"S-{year}-0005",
    ]


@pytest.mark.asyncio
async def test_different_prefixes_have_independent_sequences(session: AsyncSession) -> None:
    year = datetime.now(UTC).year
    assert await ReferenceNumberService.allocate("S", session=session) == f"S-{year}-0001"
    assert await ReferenceNumberService.allocate("INV", session=session) == f"INV-{year}-0001"
    assert await ReferenceNumberService.allocate("S", session=session) == f"S-{year}-0002"
    assert await ReferenceNumberService.allocate("INV", session=session) == f"INV-{year}-0002"
    await session.commit()


@pytest.mark.asyncio
async def test_explicit_year_defaults_to_now(session: AsyncSession) -> None:
    """No ``year=`` argument falls back to current UTC year."""
    expected_year = datetime.now(UTC).year
    ref = await ReferenceNumberService.allocate("Q", session=session)
    await session.commit()
    assert ref == f"Q-{expected_year}-0001"


@pytest.mark.asyncio
async def test_padding_override_applies(session: AsyncSession) -> None:
    rn.PADDING_OVERRIDES["WIDE"] = 6
    year = datetime.now(UTC).year
    ref = await ReferenceNumberService.allocate("WIDE", session=session)
    await session.commit()
    assert ref == f"WIDE-{year}-000001"


@pytest.mark.asyncio
async def test_overflow_logs_warning_once(
    session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    """When ``last_value`` crosses the configured padding the allocator
    logs a single warning per (prefix, padding) and keeps emitting
    references with the expanded digit count."""
    year = datetime.now(UTC).year
    rn.PADDING_OVERRIDES["X"] = 2  # threshold = 100

    # Pre-seed last_value so we don't have to do 99 allocations.
    from sqlalchemy import text

    await session.execute(
        text("INSERT INTO reference_sequence (prefix, year, last_value) " "VALUES (:p, :y, :v)"),
        {"p": "X", "y": year, "v": 99},
    )
    await session.commit()

    with caplog.at_level(logging.WARNING, logger="app.services.reference_number"):
        first = await ReferenceNumberService.allocate("X", session=session)  # -> 100
        second = await ReferenceNumberService.allocate("X", session=session)  # -> 101
        await session.commit()

    assert first == f"X-{year}-100"
    assert second == f"X-{year}-101"
    overflow_records = [
        r for r in caplog.records if "exceeded configured padding" in r.getMessage()
    ]
    assert len(overflow_records) == 1, overflow_records
