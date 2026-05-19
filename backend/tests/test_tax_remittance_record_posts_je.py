"""Recording a tax remittance posts a balanced Dr/Cr JE in the same TX (Phase 9.6, #158)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.journal_entry import JournalEntry
from app.models.tax_remittance import TaxRemittance, TaxRemittanceState
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._tax_remittance_helpers import (
    auth_header,
    post_tax_collection,
    seed_tax_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_record_posts_balanced_je(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_tax_stack(app_session)
    owner, user = await token_for(Role.OWNER, client, app_session)

    # Collect $10 tax on $100 of sales.
    await post_tax_collection(
        app_session,
        accounts=accounts,
        subtotal="100.00",
        tax="10.00",
        actor_user_id=user.id,
    )

    today = datetime.now(UTC).date()
    body = {
        "profile_id": str(accounts["profile_id"]),
        "period_start": today.replace(day=1).isoformat(),
        "period_end": today.isoformat(),
        "amount_paid": "10.00",
        "paid_on": today.isoformat(),
        "method": "ach",
        "bank_account_id": str(accounts["bank_account_id"]),
        "reference_number": "EFTPS-12345",
    }
    r = await client.post("/api/v1/tax-remittances", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["state"] == "recorded"
    assert payload["remittance_number"].startswith("TAX-")
    assert payload["posting_journal_entry_id"] is not None

    je_id = uuid.UUID(payload["posting_journal_entry_id"])
    je = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == je_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    lines = sorted(je.lines, key=lambda line: line.line_number)
    by_account = {line.account_id: line for line in lines}

    liab_line = by_account[accounts["liability_account_id"]]
    bank_line = by_account[accounts["bank_account_id"]]
    assert liab_line.debit == Decimal("10.000000")
    assert liab_line.credit == Decimal("0")
    assert bank_line.credit == Decimal("10.000000")
    assert bank_line.debit == Decimal("0")

    total_d = sum(line.debit for line in lines)
    total_c = sum(line.credit for line in lines)
    assert total_d == total_c == Decimal("10.000000")

    # DB row state
    row = (
        await app_session.execute(
            select(TaxRemittance).where(TaxRemittance.id == uuid.UUID(payload["id"]))
        )
    ).scalar_one()
    assert row.state == TaxRemittanceState.RECORDED
