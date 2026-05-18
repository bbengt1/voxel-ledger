"""Expense claim approval-queue routing (Phase 8.7, #134)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.approval_request import ApprovalRequest, ApprovalState
from app.models.expense_claim import ExpenseClaimState
from app.services import expense_claims as claims_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._expense_claims_helpers import (
    sample_claim_lines,
    seed_full_expense_claim_stack,
    seed_user,
)


@pytest.mark.asyncio
async def test_below_threshold_no_approval_request(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session, threshold=Decimal("500.00"))
    submitter = await seed_user(app_session, email="sub-low@example.com")
    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"], amount="100.00"),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    claim = await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    assert claim.state == ExpenseClaimState.SUBMITTED
    assert claim.approval_request_id is None


@pytest.mark.asyncio
async def test_at_or_above_threshold_creates_approval_request(
    app_session: AsyncSession,
) -> None:
    stack = await seed_full_expense_claim_stack(app_session, threshold=Decimal("100.00"))
    submitter = await seed_user(app_session, email="sub-high@example.com")
    # 200 >= 100 should trigger.
    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"], amount="200.00"),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    claim = await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    assert claim.approval_request_id is not None
    assert claim.state == ExpenseClaimState.SUBMITTED

    approval = (
        await app_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == claim.approval_request_id)
        )
    ).scalar_one()
    assert approval.state == ApprovalState.PENDING.value
    assert approval.subject_kind == "expense_claim"
    assert approval.subject_id == claim.id
    assert approval.request_type == "ap.expense_claim"


@pytest.mark.asyncio
async def test_approve_marks_approval_consumed(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session, threshold=Decimal("10.00"))
    submitter = await seed_user(app_session, email="sub-c@example.com")
    approver = await seed_user(app_session, email="boss-c@example.com")
    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"], amount="100.00"),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    claim = await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=approver.id)
    await app_session.commit()
    approval = (
        await app_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == claim.approval_request_id)
        )
    ).scalar_one()
    assert approval.state == ApprovalState.APPROVED.value
    assert approval.consumed_at is not None
