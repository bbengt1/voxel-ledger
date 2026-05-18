"""Inter-account transfer posts a balanced JE (Phase 8.11, #138)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    seed_bank_account,
    seed_open_period,
    token_for,
)


@pytest.mark.asyncio
async def test_transfer_posts_balanced_je(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    await seed_open_period(app_session)
    src = await seed_bank_account(app_session, code="1010", name="Checking")
    dst = await seed_bank_account(app_session, code="1011", name="Savings")

    r = await client.post(
        "/api/v1/inter-account-transfers",
        json={
            "from_account_id": str(src.id),
            "to_account_id": str(dst.id),
            "amount": "150.00",
            "occurred_at": datetime.now(UTC).isoformat(),
            "memo": "monthly sweep",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    je_id = uuid.UUID(r.json()["journal_entry_id"])

    je = (
        await app_session.execute(select(JournalEntry).where(JournalEntry.id == je_id))
    ).scalar_one()
    lines = (
        (await app_session.execute(select(JournalLine).where(JournalLine.entry_id == je.id)))
        .scalars()
        .all()
    )
    assert len(lines) == 2
    debits = {ln.account_id: ln.debit for ln in lines}
    credits = {ln.account_id: ln.credit for ln in lines}
    assert debits[dst.id] == Decimal("150.000000")
    assert credits[src.id] == Decimal("150.000000")
    assert debits[src.id] == Decimal("0.000000")
    assert credits[dst.id] == Decimal("0.000000")
