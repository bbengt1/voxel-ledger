"""Debit-XOR-credit invariant (Phase 4.2).

Both checks fire — service-layer raises ``JournalLineInvalidError`` before
the row reaches the DB. We also assert the DB CHECK is in place by
trying to bypass the service.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services import journal_entries as svc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, now_utc, seed_account, seed_owner


@pytest.mark.asyncio
async def test_both_debit_and_credit_positive_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    with pytest.raises(svc.JournalLineInvalidError):
        await svc.post(
            svc.JournalEntryInput(
                description="bad line",
                posted_at=now_utc(),
                lines=[
                    svc.JournalLineInput(
                        account_id=cash.id,
                        debit=d("10"),
                        credit=d("10"),  # invalid
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
async def test_both_debit_and_credit_zero_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    with pytest.raises(svc.JournalLineInvalidError):
        await svc.post(
            svc.JournalEntryInput(
                description="empty line",
                posted_at=now_utc(),
                lines=[
                    svc.JournalLineInput(
                        account_id=cash.id,
                        debit=d("0"),
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
async def test_db_check_constraint_catches_bypass(session: AsyncSession, engine) -> None:
    """If somehow a bad row reaches the DB, the CHECK still rejects it."""
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")

    entry = JournalEntry(
        id=uuid.uuid4(),
        entry_number="JE-2026-9999",
        posted_at=now_utc(),
        description="bypass",
        actor_user_id=owner.id,
        is_reversed=False,
    )
    session.add(entry)
    await session.flush()

    line = JournalLine(
        id=uuid.uuid4(),
        entry_id=entry.id,
        account_id=cash.id,
        debit=d("10"),
        credit=d("10"),
        line_number=1,
    )
    session.add(line)
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio
async def test_too_few_lines_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")

    with pytest.raises(svc.JournalEntryTooFewLinesError):
        await svc.post(
            svc.JournalEntryInput(
                description="single line",
                posted_at=now_utc(),
                lines=[
                    svc.JournalLineInput(
                        account_id=cash.id,
                        debit=d("10"),
                        credit=d("0"),
                        line_number=1,
                    ),
                ],
            ),
            session=session,
            actor_user_id=owner.id,
        )


@pytest.mark.asyncio
async def test_empty_description_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    with pytest.raises(svc.JournalEntryEmptyDescriptionError):
        await svc.post(
            svc.JournalEntryInput(
                description="   ",
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
