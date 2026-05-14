"""Year boundary: each ``(prefix, year)`` is its own sequence.

This test passes ``year=`` explicitly so it doesn't depend on the wall
clock — the year-default behavior is exercised in the SQLite test.
"""

from __future__ import annotations

import pytest
from app.models import Base
from app.services.reference_number import ReferenceNumberService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_year_boundary_resets_sequence(session: AsyncSession) -> None:
    for _ in range(3):
        await ReferenceNumberService.allocate("S", session=session, year=2026)
    fresh = await ReferenceNumberService.allocate("S", session=session, year=2027)
    follow = await ReferenceNumberService.allocate("S", session=session, year=2027)
    await session.commit()
    assert fresh == "S-2027-0001"
    assert follow == "S-2027-0002"


@pytest.mark.asyncio
async def test_old_year_resumes_independently(session: AsyncSession) -> None:
    """Allocating in 2027 doesn't disturb 2026's counter."""
    await ReferenceNumberService.allocate("S", session=session, year=2026)
    await ReferenceNumberService.allocate("S", session=session, year=2026)
    await ReferenceNumberService.allocate("S", session=session, year=2027)
    third_2026 = await ReferenceNumberService.allocate("S", session=session, year=2026)
    await session.commit()
    assert third_2026 == "S-2026-0003"
