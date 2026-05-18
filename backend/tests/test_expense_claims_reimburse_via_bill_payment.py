"""Marking an expense claim reimbursed (Phase 8.7, #134)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.bill_payment import BillPayment, BillPaymentMethod, BillPaymentState
from app.models.expense_claim import ExpenseClaimState
from app.services import expense_claims as claims_service
from app.services import vendors as vendors_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._expense_claims_helpers import (
    sample_claim_lines,
    seed_full_expense_claim_stack,
    seed_user,
)


@pytest.mark.asyncio
async def test_mark_reimbursed_flips_state(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="reimb-sub@example.com")
    approver = await seed_user(app_session, email="reimb-app@example.com")

    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    claim = await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=approver.id)
    await app_session.commit()

    vendor = await vendors_service.create(
        app_session,
        display_name="Employee X",
        actor_user_id=None,
    )
    bp = BillPayment(
        id=uuid.uuid4(),
        payment_number="BPAY-2026-9999",
        vendor_id=vendor.id,
        method=BillPaymentMethod.CHECK,
        amount=Decimal("50.00"),
        state=BillPaymentState.PENDING,
        created_by_user_id=approver.id,
    )
    app_session.add(bp)
    await app_session.commit()

    claim = await claims_service.mark_reimbursed(
        app_session,
        claim_id=claim.id,
        bill_payment_id=bp.id,
        actor_user_id=approver.id,
    )
    await app_session.commit()
    assert claim.state == ExpenseClaimState.REIMBURSED
    assert claim.reimbursement_payment_id == bp.id


@pytest.mark.asyncio
async def test_mark_reimbursed_unknown_payment(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="reimb2-sub@example.com")
    approver = await seed_user(app_session, email="reimb2-app@example.com")

    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    await claims_service.submit(app_session, claim_id=claim.id, actor_user_id=submitter.id)
    await app_session.commit()
    await claims_service.approve(app_session, claim_id=claim.id, actor_user_id=approver.id)
    await app_session.commit()

    with pytest.raises(claims_service.BillPaymentNotFoundForClaimError):
        await claims_service.mark_reimbursed(
            app_session,
            claim_id=claim.id,
            bill_payment_id=uuid.uuid4(),
            actor_user_id=approver.id,
        )
