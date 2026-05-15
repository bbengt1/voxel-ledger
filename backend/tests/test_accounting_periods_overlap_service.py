"""Service-side overlap rejection (Phase 4.3, #66)."""

from __future__ import annotations

from datetime import date

import pytest
from app.services import accounting_periods as svc
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import ensure_schema, seed_owner


@pytest.mark.asyncio
async def test_exact_overlap_rejected(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    await svc.create(
        "a", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    with pytest.raises(svc.OverlappingPeriodError):
        await svc.create(
            "b",
            date(1900, 1, 1),
            date(1900, 3, 31),
            session=session,
            actor_user_id=owner.id,
        )


@pytest.mark.asyncio
async def test_inclusive_boundary_overlap_rejected(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    await svc.create(
        "a", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    # Touch at boundary day (Mar 31 is inclusive in both ranges).
    with pytest.raises(svc.OverlappingPeriodError):
        await svc.create(
            "b",
            date(1900, 3, 31),
            date(1900, 6, 30),
            session=session,
            actor_user_id=owner.id,
        )


@pytest.mark.asyncio
async def test_adjacent_ranges_allowed(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    await svc.create(
        "a", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    p = await svc.create(
        "b", date(1900, 4, 1), date(1900, 6, 30), session=session, actor_user_id=owner.id
    )
    assert p.id is not None


@pytest.mark.asyncio
async def test_partial_overlap_rejected(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    await svc.create(
        "a", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    with pytest.raises(svc.OverlappingPeriodError):
        await svc.create(
            "b",
            date(1900, 3, 1),
            date(1900, 4, 30),
            session=session,
            actor_user_id=owner.id,
        )
