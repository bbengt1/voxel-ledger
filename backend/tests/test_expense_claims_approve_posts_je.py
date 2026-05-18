"""Approving an expense claim posts a balanced JE (Phase 8.7, #134)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services import expense_claims as claims_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._expense_claims_helpers import (
    sample_claim_lines,
    seed_full_expense_claim_stack,
    seed_user,
)


@pytest.mark.asyncio
async def test_approve_posts_balanced_je(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="je-sub@example.com")
    approver = await seed_user(app_session, email="je-app@example.com")

    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"], amount="75.50"),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    claim = await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=approver.id)
    await app_session.commit()

    assert claim.posting_journal_entry_id is not None
    entry = (
        await app_session.execute(
            select(JournalEntry)
            .where(JournalEntry.id == claim.posting_journal_entry_id)
            .options(selectinload(JournalEntry.lines))
        )
    ).scalar_one()
    total_debit = sum((line.debit for line in entry.lines), Decimal("0"))
    total_credit = sum((line.credit for line in entry.lines), Decimal("0"))
    assert total_debit == total_credit
    assert total_debit == Decimal("75.500000")

    # The Cr leg should hit the employee-reimbursable account.
    credit_lines = [line for line in entry.lines if line.credit > 0]
    assert len(credit_lines) == 1
    assert credit_lines[0].account_id == stack["reimbursable_account_id"]

    # The Dr leg should hit the expense account (resolved via category).
    debit_lines = [line for line in entry.lines if line.debit > 0]
    assert all(line.account_id == stack["expense_account_id"] for line in debit_lines)


@pytest.mark.asyncio
async def test_approve_multi_line_je(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="je-multi-sub@example.com")
    approver = await seed_user(app_session, email="je-multi-app@example.com")

    from datetime import UTC, datetime

    lines = [
        {
            "expense_category_id": str(stack["expense_category_id"]),
            "description": "Taxi",
            "amount": "20.00",
            "occurred_on": datetime.now(UTC).date().isoformat(),
        },
        {
            "expense_category_id": str(stack["expense_category_id"]),
            "description": "Hotel",
            "amount": "150.00",
            "occurred_on": datetime.now(UTC).date().isoformat(),
        },
    ]
    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=lines,
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    claim = await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=approver.id)
    await app_session.commit()
    assert claim.total_amount == Decimal("170.000000")

    je_lines = (
        (
            await app_session.execute(
                select(JournalLine).where(JournalLine.entry_id == claim.posting_journal_entry_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(list(je_lines)) == 3  # 2 Dr + 1 Cr


@pytest.mark.asyncio
async def test_approve_without_reimbursable_setting_raises(
    app_session: AsyncSession,
) -> None:
    import uuid as _uuid
    from datetime import UTC, datetime, timedelta

    from app.models.account import Account
    from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
    from app.services import expense_categories as expense_categories_service

    today = datetime.now(UTC).date()
    app_session.add(
        AccountingPeriod(
            id=_uuid.uuid4(),
            name="phase87-noreimb",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=30),
            state=AccountingPeriodState.OPEN.value,
        )
    )
    expense_account = Account(id=_uuid.uuid4(), code="5101", name="X", type="expense")
    app_session.add(expense_account)
    await app_session.flush()
    category = await expense_categories_service.create(
        app_session,
        code=f"X-{_uuid.uuid4().hex[:6]}",
        name="X",
        default_expense_account_id=expense_account.id,
        actor_user_id=None,
    )
    await app_session.commit()
    submitter = await seed_user(app_session, email="noreimb-sub@example.com")
    approver = await seed_user(app_session, email="noreimb-app@example.com")

    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=category.id, amount="10.00"),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    with pytest.raises(claims_service.MissingReimbursableAccountError):
        await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=approver.id)
