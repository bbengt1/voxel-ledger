"""Acquiring a fixed asset posts Dr Asset / Cr Bank in the same TX (Phase 9.1, #153)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.journal_entry import JournalEntry
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_acquire_posts_balanced_je(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    body = sample_acquire_body(accounts=accounts, cost="2500.00")
    r = await client.post("/api/v1/fixed-assets", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    je_id = uuid.UUID(payload["posting_journal_entry_id"])

    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == je_id)
        .options(selectinload(JournalEntry.lines))
    )
    je = (await app_session.execute(stmt)).scalar_one()
    lines = sorted(je.lines, key=lambda line: line.line_number)
    assert len(lines) == 2

    by_account = {line.account_id: line for line in lines}
    asset_line = by_account[accounts["asset_account_id"]]
    bank_line = by_account[accounts["bank_account_id"]]

    assert asset_line.debit == Decimal("2500.000000")
    assert asset_line.credit == Decimal("0")
    assert bank_line.credit == Decimal("2500.000000")
    assert bank_line.debit == Decimal("0")

    total_d = sum(line.debit for line in lines)
    total_c = sum(line.credit for line in lines)
    assert total_d == total_c == Decimal("2500.000000")
