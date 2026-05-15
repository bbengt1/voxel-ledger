"""Accounting-period state-machine transitions (Phase 4.3, #66)."""

from __future__ import annotations

from datetime import date

import pytest
from app.models.accounting_period import AccountingPeriodState
from app.services import accounting_periods as svc
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import ensure_schema, seed_owner


async def _create_period(session: AsyncSession, owner_id):
    return await svc.create(
        "2026-Q1",
        date(2026, 1, 1),
        date(2026, 3, 31),
        session=session,
        actor_user_id=owner_id,
    )


@pytest.mark.asyncio
async def test_open_to_closed(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    p2 = await svc.close(p.id, session=session, actor_user_id=owner.id)
    assert p2.state == AccountingPeriodState.CLOSED.value
    assert p2.closed_at is not None
    assert p2.closed_by_user_id == owner.id


@pytest.mark.asyncio
async def test_closed_to_open(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    await svc.close(p.id, session=session, actor_user_id=owner.id)
    reopened = await svc.reopen(p.id, session=session, actor_user_id=owner.id)
    assert reopened.state == AccountingPeriodState.OPEN.value
    assert reopened.closed_at is None
    assert reopened.closed_by_user_id is None


@pytest.mark.asyncio
async def test_closed_to_locked(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    await svc.close(p.id, session=session, actor_user_id=owner.id)
    locked = await svc.lock(p.id, session=session, actor_user_id=owner.id)
    assert locked.state == AccountingPeriodState.LOCKED.value
    assert locked.locked_at is not None
    assert locked.locked_by_user_id == owner.id


@pytest.mark.asyncio
async def test_open_to_locked_prohibited(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    with pytest.raises(svc.IllegalPeriodTransitionError):
        await svc.lock(p.id, session=session, actor_user_id=owner.id)


@pytest.mark.asyncio
async def test_locked_rejects_close_and_reopen(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    await svc.close(p.id, session=session, actor_user_id=owner.id)
    await svc.lock(p.id, session=session, actor_user_id=owner.id)
    with pytest.raises(svc.IllegalPeriodTransitionError):
        await svc.close(p.id, session=session, actor_user_id=owner.id)
    with pytest.raises(svc.IllegalPeriodTransitionError):
        await svc.reopen(p.id, session=session, actor_user_id=owner.id)


@pytest.mark.asyncio
async def test_close_open_period_rejects_double_close(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    await svc.close(p.id, session=session, actor_user_id=owner.id)
    with pytest.raises(svc.IllegalPeriodTransitionError):
        await svc.close(p.id, session=session, actor_user_id=owner.id)


@pytest.mark.asyncio
async def test_reopen_open_period_rejected(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    with pytest.raises(svc.IllegalPeriodTransitionError):
        await svc.reopen(p.id, session=session, actor_user_id=owner.id)


@pytest.mark.asyncio
async def test_update_name_only(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    p = await svc.create(
        "p1", date(1900, 1, 1), date(1900, 12, 31), session=session, actor_user_id=owner.id
    )
    updated = await svc.update(p.id, name="renamed", session=session, actor_user_id=owner.id)
    assert updated.name == "renamed"


@pytest.mark.asyncio
async def test_invalid_dates_rejected(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    with pytest.raises(svc.InvalidPeriodDatesError):
        await svc.create(
            "bad", date(1900, 2, 1), date(1900, 1, 1), session=session, actor_user_id=owner.id
        )
