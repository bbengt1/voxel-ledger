"""Service-layer tests for the chart-of-accounts (Phase 4.1)."""

from __future__ import annotations

import uuid

import pytest
from app.events.types import accounting as accounting_events
from app.models import Base
from app.models.event import Event
from app.services import accounts as svc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _ensure_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_create_duplicate_active_code_raises(session: AsyncSession, engine) -> None:
    await _ensure_schema(engine)
    await svc.create(session, code="1000", name="Assets", type="asset", actor_user_id=None)
    with pytest.raises(svc.DuplicateAccountCodeError):
        await svc.create(session, code="1000", name="Other", type="asset", actor_user_id=None)


@pytest.mark.asyncio
async def test_archived_code_can_be_reused(session: AsyncSession, engine) -> None:
    await _ensure_schema(engine)
    a = await svc.create(session, code="1000", name="Assets", type="asset", actor_user_id=None)
    await svc.archive(session, account_id=a.id, actor_user_id=None)
    b = await svc.create(session, code="1000", name="Assets v2", type="asset", actor_user_id=None)
    assert b.id != a.id
    assert b.is_archived is False


@pytest.mark.asyncio
async def test_patch_rejects_immutable_code(session: AsyncSession, engine) -> None:
    await _ensure_schema(engine)
    a = await svc.create(session, code="1000", name="Assets", type="asset", actor_user_id=None)
    with pytest.raises(svc.ImmutableFieldError):
        await svc.update(
            session,
            account_id=a.id,
            patch={"code": "1001"},
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_patch_rejects_immutable_type(session: AsyncSession, engine) -> None:
    await _ensure_schema(engine)
    a = await svc.create(session, code="1000", name="Assets", type="asset", actor_user_id=None)
    with pytest.raises(svc.ImmutableFieldError):
        await svc.update(
            session,
            account_id=a.id,
            patch={"type": "expense"},
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_update_emits_diff(session: AsyncSession, engine) -> None:
    await _ensure_schema(engine)
    a = await svc.create(session, code="1000", name="Assets", type="asset", actor_user_id=None)
    await svc.update(
        session,
        account_id=a.id,
        patch={"name": "Total Assets"},
        actor_user_id=None,
    )
    rows = (
        (
            await session.execute(
                select(Event).where(Event.type == accounting_events.TYPE_ACCOUNT_UPDATED)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    payload = rows[0].payload
    assert payload["before"] == {"name": "Assets"}
    assert payload["after"] == {"name": "Total Assets"}


@pytest.mark.asyncio
async def test_create_with_unknown_parent_raises(session: AsyncSession, engine) -> None:
    await _ensure_schema(engine)
    with pytest.raises(svc.ParentNotFoundError):
        await svc.create(
            session,
            code="1010",
            name="Cash",
            type="asset",
            parent_account_id=uuid.uuid4(),
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_list_cursor_pagination_orders_by_code(session: AsyncSession, engine) -> None:
    await _ensure_schema(engine)
    for code in ["1000", "2000", "3000", "4000"]:
        await svc.create(session, code=code, name=code, type="asset", actor_user_id=None)
    page = await svc.list_accounts(session, limit=2)
    assert [a.code for a in page.items] == ["1000", "2000"]
    assert page.next_cursor is not None
    page2 = await svc.list_accounts(session, limit=2, cursor=page.next_cursor)
    assert [a.code for a in page2.items] == ["3000", "4000"]
