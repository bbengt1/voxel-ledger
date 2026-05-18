"""Manual match endpoint (Phase 8.10, #137)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.bank import BankTransactionState
from app.services import journal_entries as journal_service
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
async def test_manual_match_links_to_existing_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    token = await token_for(Role.OWNER, client, app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)

    # Pre-post a JE that touches the bank account.
    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description="prebuilt JE",
            posted_at=datetime.now(UTC),
            lines=[
                journal_service.JournalLineInput(
                    account_id=expense.id,
                    debit=Decimal("12.00"),
                    credit=Decimal("0"),
                    line_number=1,
                ),
                journal_service.JournalLineInput(
                    account_id=bank.id,
                    debit=Decimal("0"),
                    credit=Decimal("12.00"),
                    line_number=2,
                ),
            ],
        ),
        session=app_session,
        actor_user_id=user.id,
        _internal_skip_approval_check=True,
    )
    await app_session.commit()

    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="ANY",
        amount=Decimal("-12.00"),
    )

    r = await client.post(
        f"/api/v1/bank-transactions/{tx.id}/match",
        json={"journal_entry_id": str(entry.id)},
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "matched"
    assert r.json()["matched_journal_line_id"] is not None

    await app_session.refresh(tx)
    assert tx.state == BankTransactionState.MATCHED


@pytest.mark.asyncio
async def test_manual_match_rejects_je_without_bank_line(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    token = await token_for(Role.OWNER, client, app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session, code="6001", name="Other Expense")
    other = await seed_expense_account(app_session, code="6002", name="Misc")

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description="je without bank",
            posted_at=datetime.now(UTC),
            lines=[
                journal_service.JournalLineInput(
                    account_id=expense.id,
                    debit=Decimal("5"),
                    credit=Decimal("0"),
                    line_number=1,
                ),
                journal_service.JournalLineInput(
                    account_id=other.id,
                    debit=Decimal("0"),
                    credit=Decimal("5"),
                    line_number=2,
                ),
            ],
        ),
        session=app_session,
        actor_user_id=user.id,
        _internal_skip_approval_check=True,
    )
    await app_session.commit()

    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="UNRELATED",
        amount=Decimal("-5.00"),
    )

    r = await client.post(
        f"/api/v1/bank-transactions/{tx.id}/match",
        json={"journal_entry_id": str(entry.id)},
        headers=auth_header(token),
    )
    assert r.status_code == 400
