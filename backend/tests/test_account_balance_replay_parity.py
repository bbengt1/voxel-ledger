"""Replay parity for account_balance (Phase 4.2)."""

from __future__ import annotations

import pytest
from app.models import Base
from app.models.account_balance import AccountBalance
from app.models.projection import ProjectionCursor
from app.projections import registry as projection_registry
from app.projections.account_balance import HANDLER_NAME
from app.projections.replay import replay_handler, truncate_read_model_tables
from app.services import journal_entries as svc
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests._je_helpers import d, now_utc, seed_account, seed_owner


@pytest.mark.asyncio
async def test_replay_parity(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as s:
        owner = await seed_owner(s)
        cash = await seed_account(s, code="1000", name="Cash", type="asset")
        revenue = await seed_account(s, code="4000", name="Revenue", type="revenue")

        # Mix of posts.
        for _ in range(3):
            await svc.post(
                svc.JournalEntryInput(
                    description="sale",
                    posted_at=now_utc(),
                    lines=[
                        svc.JournalLineInput(
                            account_id=cash.id, debit=d("25"), credit=d("0"), line_number=1
                        ),
                        svc.JournalLineInput(
                            account_id=revenue.id, debit=d("0"), credit=d("25"), line_number=2
                        ),
                    ],
                ),
                session=s,
                actor_user_id=owner.id,
            )
        # Reverse one of them.
        first = await svc.list_entries(session=s, limit=10)
        await svc.reverse(first.items[-1].id, session=s, actor_user_id=owner.id)
        await s.commit()

    async with factory() as s:
        before = {
            r.account_id: (r.total_debits, r.total_credits)
            for r in (await s.execute(select(AccountBalance))).scalars()
        }
    assert before

    # Truncate + reset cursor.
    async with factory() as s:
        await truncate_read_model_tables(s, ("account_balance",))
        await s.execute(
            delete(ProjectionCursor).where(ProjectionCursor.handler_name == HANDLER_NAME)
        )
        await s.commit()

    # Replay.
    handler = projection_registry.get_handler(HANDLER_NAME)
    await replay_handler(handler, factory, from_position=0)

    async with factory() as s:
        after = {
            r.account_id: (r.total_debits, r.total_credits)
            for r in (await s.execute(select(AccountBalance))).scalars()
        }
    assert after == before
