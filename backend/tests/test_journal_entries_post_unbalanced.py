"""Unbalanced posts must fail with a clear delta (Phase 4.2)."""

from __future__ import annotations

import pytest
from app.services import journal_entries as svc
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, ensure_schema, now_utc, seed_account, seed_owner


@pytest.mark.asyncio
async def test_one_cent_imbalance_raises(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    owner = await seed_owner(session)
    cash = await seed_account(session, code="1000", name="Cash", type="asset")
    revenue = await seed_account(session, code="4000", name="Revenue", type="revenue")

    with pytest.raises(svc.JournalEntryUnbalancedError) as excinfo:
        await svc.post(
            svc.JournalEntryInput(
                description="off by a penny",
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
                        credit=d("99.99"),
                        line_number=2,
                    ),
                ],
            ),
            session=session,
            actor_user_id=owner.id,
        )
    msg = str(excinfo.value)
    assert "delta" in msg
    assert "0.01" in msg
