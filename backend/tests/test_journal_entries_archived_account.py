"""Posting against an archived account fails (Phase 4.2)."""

from __future__ import annotations

import pytest
from app.services import journal_entries as svc
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, now_utc, seed_account, seed_owner


@pytest.mark.asyncio
async def test_archived_account_blocks_post(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(
        session, code="4000", name="Revenue", type="revenue", is_archived=True
    )

    with pytest.raises(svc.AccountArchivedError):
        await svc.post(
            svc.JournalEntryInput(
                description="post to archived",
                posted_at=now_utc(),
                lines=[
                    svc.JournalLineInput(
                        account_id=cash.id,
                        debit=d("10"),
                        credit=d("0"),
                        line_number=1,
                    ),
                    svc.JournalLineInput(
                        account_id=revenue.id,
                        debit=d("0"),
                        credit=d("10"),
                        line_number=2,
                    ),
                ],
            ),
            session=session,
            actor_user_id=owner.id,
        )


@pytest.mark.asyncio
async def test_unknown_account_blocks_post(session: AsyncSession, engine) -> None:
    import uuid

    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")

    with pytest.raises(svc.AccountNotFoundError):
        await svc.post(
            svc.JournalEntryInput(
                description="unknown account",
                posted_at=now_utc(),
                lines=[
                    svc.JournalLineInput(
                        account_id=cash.id,
                        debit=d("10"),
                        credit=d("0"),
                        line_number=1,
                    ),
                    svc.JournalLineInput(
                        account_id=uuid.uuid4(),
                        debit=d("0"),
                        credit=d("10"),
                        line_number=2,
                    ),
                ],
            ),
            session=session,
            actor_user_id=owner.id,
        )
