"""Expense claim state machine (Phase 8.7, #134)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.expense_claim import ExpenseClaimState
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.services import expense_claims as claims_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._expense_claims_helpers import (
    sample_claim_lines,
    seed_full_expense_claim_stack,
    seed_user,
)


@pytest.mark.asyncio
async def test_create_draft_then_submit_then_approve(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session, threshold=Decimal("1000.00"))
    submitter = await seed_user(app_session, email="emp@example.com")
    approver = await seed_user(app_session, email="boss@example.com")

    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"], amount="50.00"),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    assert claim.state == ExpenseClaimState.DRAFT
    assert claim.claim_number.startswith("EXP-")
    assert claim.total_amount == Decimal("50.000000")

    claim = await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    assert claim.state == ExpenseClaimState.SUBMITTED
    # Below threshold, no approval request.
    assert claim.approval_request_id is None

    claim = await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=approver.id)
    await app_session.commit()
    assert claim.state == ExpenseClaimState.APPROVED
    # QBO is the sole ledger (epic #312, Phase 5e): no local JE — the posting
    # goes out via the sync outbox.
    assert claim.posting_journal_entry_id is None
    assert claim.approver_user_id == approver.id

    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "expense_claim", QboSyncOutbox.local_id == claim.id
            )
        )
    ).scalar_one()
    by_role = {ln["role"]: ln for ln in outbox_row.payload["lines"]}
    assert by_role["expense"]["posting"] == "debit"
    assert by_role["employee_reimbursable"]["posting"] == "credit"
    assert Decimal(by_role["employee_reimbursable"]["amount"]) == Decimal("50.00")


@pytest.mark.asyncio
async def test_reject_from_submitted(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="emp-rej@example.com")
    approver = await seed_user(app_session, email="boss-rej@example.com")

    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()

    claim = await claims_service.reject(
        app_session,
        claim_id=claim.id,
        actor_user_id=approver.id,
        rejection_reason="not a business expense",
    )
    await app_session.commit()
    assert claim.state == ExpenseClaimState.REJECTED
    assert claim.rejection_reason == "not a business expense"
    assert claim.posting_journal_entry_id is None


@pytest.mark.asyncio
async def test_cancel_from_draft(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="emp-cancel@example.com")
    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    claim = await claims_service.cancel(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    assert claim.state == ExpenseClaimState.CANCELLED


@pytest.mark.asyncio
async def test_cancel_from_submitted_rejects_approval(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session, threshold=Decimal("10.00"))
    submitter = await seed_user(app_session, email="emp-cs@example.com")
    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"], amount="100.00"),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    claim = await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    assert claim.approval_request_id is not None

    claim = await claims_service.cancel(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    assert claim.state == ExpenseClaimState.CANCELLED


@pytest.mark.asyncio
async def test_illegal_transition_raises(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="emp-ill@example.com")
    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    # Can't approve a draft.
    with pytest.raises(claims_service.InvalidExpenseClaimStateError):
        await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=submitter.id)
