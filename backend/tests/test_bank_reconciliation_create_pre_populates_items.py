"""Reconciliation pre-populates items from the period (Phase 8.11, #138)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.bank import BankTransactionState
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    seed_bank_account,
    seed_bank_transaction,
    token_for,
)


@pytest.mark.asyncio
async def test_create_reconciliation_pre_populates_items(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)

    today = datetime.now(UTC).date()
    period_start = today - timedelta(days=30)
    period_end = today

    # Two txs in period — one matched (initial cleared), one unmatched.
    tx1 = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="COFFEE",
        amount=Decimal("-4.50"),
        occurred_on=period_start + timedelta(days=2),
    )
    tx1.state = BankTransactionState.MATCHED
    await app_session.commit()

    tx2 = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="PAYROLL",
        amount=Decimal("2500.00"),
        occurred_on=period_start + timedelta(days=5),
    )

    # One ignored tx — must NOT appear in items.
    tx_ignored = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="DUPE",
        amount=Decimal("-99.00"),
        occurred_on=period_start + timedelta(days=6),
    )
    tx_ignored.state = BankTransactionState.IGNORED
    await app_session.commit()

    # One tx OUTSIDE the period — must NOT appear.
    await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="OLD",
        amount=Decimal("-10.00"),
        occurred_on=period_start - timedelta(days=1),
    )

    r = await client.post(
        "/api/v1/bank-reconciliations",
        json={
            "account_id": str(bank.id),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "statement_ending_balance": "0.00",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    items = body["items"]
    assert len(items) == 2
    by_tx = {i["bank_transaction_id"]: i for i in items}
    assert by_tx[str(tx1.id)]["is_cleared"] is True  # matched -> True
    assert by_tx[str(tx2.id)]["is_cleared"] is False  # unmatched -> False
    assert str(tx_ignored.id) not in by_tx
