"""Auto-match worker: basic ``contains`` match end-to-end (Phase 8.10, #137)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.bank import BankTransactionState
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.services import bank_auto_matcher, bank_match_rules
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    seed_bank_account,
    seed_bank_transaction,
    seed_expense_account,
    seed_open_period,
    seed_user,
)


@pytest.mark.asyncio
async def test_contains_match_posts_je_and_flips_state(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)

    await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="COFFEE",
        action_kind="post_to_account",
        debit_account_id=expense.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    await app_session.commit()

    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="COFFEE SHOP downtown",
        amount=Decimal("-4.50"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()

    assert len(results) == 1
    assert results[0].action_kind == "post_to_account"
    # QBO is the sole ledger (epic #312, Phase 5e): no local JE — the match
    # is pushed via the sync outbox instead.
    assert results[0].journal_entry_id is None

    await app_session.refresh(tx)
    assert tx.state == BankTransactionState.MATCHED
    assert tx.matched_journal_line_id is None

    row = (
        await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "bank_match"))
    ).scalar_one()
    assert row.local_id == tx.id
    assert {(ln["posting"], Decimal(ln["amount"])) for ln in row.payload["lines"]} == {
        ("debit", Decimal("4.50")),
        ("credit", Decimal("4.50")),
    }
