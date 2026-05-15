"""find_period_for: date inside / boundary / outside (Phase 4.3, #66)."""

from __future__ import annotations

from datetime import date

import pytest
from app.services import accounting_periods as svc
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import ensure_schema, seed_owner


@pytest.mark.asyncio
async def test_find_period_for_inside(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    hit = await svc.find_period_for(date(1900, 2, 15), session=session)
    assert hit is not None
    assert hit.id == p.id


@pytest.mark.asyncio
async def test_find_period_for_start_boundary(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    hit = await svc.find_period_for(date(1900, 1, 1), session=session)
    assert hit is not None and hit.id == p.id


@pytest.mark.asyncio
async def test_find_period_for_end_boundary(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    hit = await svc.find_period_for(date(1900, 3, 31), session=session)
    assert hit is not None and hit.id == p.id


@pytest.mark.asyncio
async def test_find_period_for_outside_returns_none(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    await svc.create(
        "p", date(1900, 1, 1), date(1900, 3, 31), session=session, actor_user_id=owner.id
    )
    assert (await svc.find_period_for(date(1899, 12, 31), session=session)) is None
    assert (await svc.find_period_for(date(1900, 4, 1), session=session)) is None
