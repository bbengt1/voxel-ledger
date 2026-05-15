"""Balanced post + balance-projection updates (Phase 4.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.account_balance import AccountBalance
from app.services import journal_entries as svc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, now_utc, seed_account, seed_owner


@pytest.mark.asyncio
async def test_balanced_post_updates_account_balance(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    entry = await svc.post(
        svc.JournalEntryInput(
            description="opening sale",
            posted_at=now_utc(),
            lines=[
                svc.JournalLineInput(
                    account_id=cash.id,
                    debit=d("100.00"),
                    credit=d("0"),
                    line_number=1,
                ),
                svc.JournalLineInput(
                    account_id=revenue.id,
                    debit=d("0"),
                    credit=d("100.00"),
                    line_number=2,
                ),
            ],
        ),
        session=session,
        actor_user_id=owner.id,
    )
    assert entry.entry_number.startswith("JE-")
    assert entry.is_reversed is False
    assert len(entry.lines) == 2

    rows = (await session.execute(select(AccountBalance))).scalars().all()
    by_account = {r.account_id: r for r in rows}
    assert by_account[cash.id].total_debits == Decimal("100.000000")
    assert by_account[cash.id].total_credits == Decimal("0.000000")
    assert by_account[revenue.id].total_debits == Decimal("0.000000")
    assert by_account[revenue.id].total_credits == Decimal("100.000000")


@pytest.mark.asyncio
async def test_balanced_post_accumulates_per_account(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    for _ in range(3):
        await svc.post(
            svc.JournalEntryInput(
                description="repeated sale",
                posted_at=now_utc(),
                lines=[
                    svc.JournalLineInput(
                        account_id=cash.id,
                        debit=d("50"),
                        credit=d("0"),
                        line_number=1,
                    ),
                    svc.JournalLineInput(
                        account_id=revenue.id,
                        debit=d("0"),
                        credit=d("50"),
                        line_number=2,
                    ),
                ],
            ),
            session=session,
            actor_user_id=owner.id,
        )

    rows = (await session.execute(select(AccountBalance))).scalars().all()
    by_account = {r.account_id: r for r in rows}
    assert by_account[cash.id].total_debits == Decimal("150.000000")
    assert by_account[revenue.id].total_credits == Decimal("150.000000")
