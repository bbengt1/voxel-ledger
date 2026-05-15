"""Reversal flow (Phase 4.2).

- Swaps debits/credits.
- Marks the original ``is_reversed = true``.
- Refuses to reverse twice.
- Refuses to reverse a reversal.
- Balances net to zero after a reversal.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.account_balance import AccountBalance
from app.services import journal_entries as svc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, now_utc, seed_account, seed_owner


async def _balanced_pair(session, owner, cash, revenue):
    return await svc.post(
        svc.JournalEntryInput(
            description="sale",
            posted_at=now_utc(),
            lines=[
                svc.JournalLineInput(
                    account_id=cash.id, debit=d("100"), credit=d("0"), line_number=1
                ),
                svc.JournalLineInput(
                    account_id=revenue.id, debit=d("0"), credit=d("100"), line_number=2
                ),
            ],
        ),
        session=session,
        actor_user_id=owner.id,
    )


@pytest.mark.asyncio
async def test_reverse_swaps_and_flags_original(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    original = await _balanced_pair(session, owner, cash, revenue)
    reversal = await svc.reverse(original.id, session=session, actor_user_id=owner.id)

    # Reversal references original.
    assert reversal.reversal_of_entry_id == original.id
    # Lines swapped: account 1000 was debited 100 originally → now credited 100.
    lines_by_account = {line.account_id: line for line in reversal.lines}
    assert lines_by_account[cash.id].debit == Decimal("0.000000")
    assert lines_by_account[cash.id].credit == Decimal("100.000000")
    assert lines_by_account[revenue.id].debit == Decimal("100.000000")
    assert lines_by_account[revenue.id].credit == Decimal("0.000000")

    # Description defaults to "Reversal of ...".
    assert reversal.description.startswith("Reversal of ")

    # Original is flagged.
    refetched = await svc.get(original.id, session=session)
    assert refetched.is_reversed is True

    # Net balance: zero on both accounts.
    rows = (await session.execute(select(AccountBalance))).scalars().all()
    by_account = {r.account_id: r for r in rows}
    assert by_account[cash.id].total_debits == by_account[cash.id].total_credits
    assert by_account[revenue.id].total_debits == by_account[revenue.id].total_credits


@pytest.mark.asyncio
async def test_cannot_reverse_twice(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    original = await _balanced_pair(session, owner, cash, revenue)
    await svc.reverse(original.id, session=session, actor_user_id=owner.id)

    with pytest.raises(svc.JournalEntryAlreadyReversedError):
        await svc.reverse(original.id, session=session, actor_user_id=owner.id)


@pytest.mark.asyncio
async def test_cannot_reverse_a_reversal(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    original = await _balanced_pair(session, owner, cash, revenue)
    reversal = await svc.reverse(original.id, session=session, actor_user_id=owner.id)

    with pytest.raises(svc.JournalEntryIsReversalError):
        await svc.reverse(reversal.id, session=session, actor_user_id=owner.id)


@pytest.mark.asyncio
async def test_reversed_event_is_balance_noop(session: AsyncSession, engine) -> None:
    """The Reversed event itself does not move balances — the
    cancelling Posted event already did."""
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    original = await _balanced_pair(session, owner, cash, revenue)
    await svc.reverse(original.id, session=session, actor_user_id=owner.id)

    rows = (await session.execute(select(AccountBalance))).scalars().all()
    by_account = {r.account_id: r for r in rows}
    # Each side ended at 100 debits and 100 credits — equal because the
    # reversal entry's Posted event cancelled the original.
    assert by_account[cash.id].total_debits == Decimal("100.000000")
    assert by_account[cash.id].total_credits == Decimal("100.000000")
    assert by_account[revenue.id].total_debits == Decimal("100.000000")
    assert by_account[revenue.id].total_credits == Decimal("100.000000")
