"""Journal entries carry an optional ``division_id`` per line (Phase 4.5).

The persisted row + the ``JournalEntryPosted`` event payload both surface
``division_id``.
"""

from __future__ import annotations

import pytest
from app.models.division import Division
from app.models.event import Event
from app.services import journal_entries as je
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, now_utc, seed_account, seed_owner


@pytest.mark.asyncio
async def test_division_id_persists_and_appears_in_event(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")
    division = Division(name="Consulting", code="CON", is_archived=False)
    session.add(division)
    await session.flush()

    entry = await je.post(
        je.JournalEntryInput(
            description="consulting sale",
            posted_at=now_utc(),
            lines=[
                je.JournalLineInput(
                    account_id=cash.id,
                    debit=d("100"),
                    credit=d("0"),
                    line_number=1,
                    division_id=division.id,
                ),
                je.JournalLineInput(
                    account_id=revenue.id,
                    debit=d("0"),
                    credit=d("100"),
                    line_number=2,
                    division_id=division.id,
                ),
            ],
        ),
        session=session,
        actor_user_id=owner.id,
    )

    assert all(line.division_id == division.id for line in entry.lines)

    event = (
        (await session.execute(select(Event).where(Event.type == "accounting.JournalEntryPosted")))
        .scalars()
        .one()
    )
    assert all(line["division_id"] == str(division.id) for line in event.payload["lines"])


@pytest.mark.asyncio
async def test_division_id_optional(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    entry = await je.post(
        je.JournalEntryInput(
            description="no division",
            posted_at=now_utc(),
            lines=[
                je.JournalLineInput(
                    account_id=cash.id, debit=d("50"), credit=d("0"), line_number=1
                ),
                je.JournalLineInput(
                    account_id=revenue.id, debit=d("0"), credit=d("50"), line_number=2
                ),
            ],
        ),
        session=session,
        actor_user_id=owner.id,
    )
    assert all(line.division_id is None for line in entry.lines)
