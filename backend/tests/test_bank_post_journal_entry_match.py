"""Manual post-journal-entry + match (Phase 8.10, #137)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    seed_bank_account,
    seed_bank_transaction,
    seed_expense_account,
    seed_open_period,
    seed_user,
    token_for,
)


@pytest.mark.asyncio
async def test_post_je_and_match(client: AsyncClient, app_session: AsyncSession) -> None:
    await seed_user(app_session)
    token = await token_for(Role.OWNER, client, app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)

    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="OFFICE SUPPLIES",
        amount=Decimal("-42.00"),
    )

    posted_at = datetime.now(UTC).isoformat()
    r = await client.post(
        f"/api/v1/bank-transactions/{tx.id}/post-journal-entry",
        json={
            "description": "office supplies",
            "posted_at": posted_at,
            "lines": [
                {
                    "account_id": str(expense.id),
                    "debit": "42",
                    "credit": "0",
                    "line_number": 1,
                },
                {
                    "account_id": str(bank.id),
                    "debit": "0",
                    "credit": "42",
                    "line_number": 2,
                },
            ],
        },
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "matched"
    assert body["matched_journal_line_id"] is not None


@pytest.mark.asyncio
async def test_post_je_rejects_without_bank_line(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await seed_user(app_session)
    token = await token_for(Role.OWNER, client, app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    a = await seed_expense_account(app_session, code="6100", name="A")
    b = await seed_expense_account(app_session, code="6200", name="B")

    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="MYSTERY",
        amount=Decimal("-10.00"),
    )

    posted_at = datetime.now(UTC).isoformat()
    r = await client.post(
        f"/api/v1/bank-transactions/{tx.id}/post-journal-entry",
        json={
            "description": "lines without bank ref",
            "posted_at": posted_at,
            "lines": [
                {
                    "account_id": str(a.id),
                    "debit": "10",
                    "credit": "0",
                    "line_number": 1,
                },
                {
                    "account_id": str(b.id),
                    "debit": "0",
                    "credit": "10",
                    "line_number": 2,
                },
            ],
        },
        headers=auth_header(token),
    )
    assert r.status_code == 400
