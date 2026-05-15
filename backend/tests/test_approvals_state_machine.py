"""State-machine: legal vs prohibited approval transitions (Phase 4.4)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.approvals import (
    ApprovalAlreadyConsumedError,
    ApprovalAlreadyDecidedError,
    ApprovalCancelForbiddenError,
    ApprovalNotApprovedError,
    ApprovalsService,
    SelfApprovalError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests._approvals_helpers import make_pending, seed_user
from tests._je_helpers import ensure_schema


@pytest.mark.asyncio
async def test_pending_to_approved(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    approved = await ApprovalsService.approve(
        req.id,
        session=session,
        approver_user_id=approver.id,
        decision_note="lgtm",
    )
    assert approved.state == "approved"
    assert approved.decided_by_user_id == approver.id


@pytest.mark.asyncio
async def test_cannot_approve_twice(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    await ApprovalsService.approve(req.id, session=session, approver_user_id=approver.id)
    with pytest.raises(ApprovalAlreadyDecidedError):
        await ApprovalsService.approve(req.id, session=session, approver_user_id=approver.id)


@pytest.mark.asyncio
async def test_cannot_reject_after_approval(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    await ApprovalsService.approve(req.id, session=session, approver_user_id=approver.id)
    with pytest.raises(ApprovalAlreadyDecidedError):
        await ApprovalsService.reject(req.id, session=session, approver_user_id=approver.id)


@pytest.mark.asyncio
async def test_cannot_cancel_after_rejection(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    await ApprovalsService.reject(req.id, session=session, approver_user_id=approver.id)
    with pytest.raises(ApprovalAlreadyDecidedError):
        await ApprovalsService.cancel(
            req.id,
            session=session,
            actor_user_id=requester.id,
            actor_is_owner=True,
        )


@pytest.mark.asyncio
async def test_requester_can_cancel(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.SALES)
    req = await make_pending(session, requester=requester)
    cancelled = await ApprovalsService.cancel(
        req.id,
        session=session,
        actor_user_id=requester.id,
        actor_is_owner=False,
    )
    assert cancelled.state == "cancelled"


@pytest.mark.asyncio
async def test_owner_can_cancel_other_request(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.SALES)
    owner = await seed_user(session, email="o@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    cancelled = await ApprovalsService.cancel(
        req.id,
        session=session,
        actor_user_id=owner.id,
        actor_is_owner=True,
    )
    assert cancelled.state == "cancelled"


@pytest.mark.asyncio
async def test_non_owner_third_party_cannot_cancel(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.SALES)
    other = await seed_user(session, email="o@x.com", role=Role.BOOKKEEPER)
    req = await make_pending(session, requester=requester)
    with pytest.raises(ApprovalCancelForbiddenError):
        await ApprovalsService.cancel(
            req.id,
            session=session,
            actor_user_id=other.id,
            actor_is_owner=False,
        )


@pytest.mark.asyncio
async def test_mark_consumed_only_on_approved(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    with pytest.raises(ApprovalNotApprovedError):
        await ApprovalsService.mark_consumed(req.id, session=session)


@pytest.mark.asyncio
async def test_mark_consumed_idempotency(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    await ApprovalsService.approve(req.id, session=session, approver_user_id=approver.id)
    await ApprovalsService.mark_consumed(req.id, session=session)
    with pytest.raises(ApprovalAlreadyConsumedError):
        await ApprovalsService.mark_consumed(req.id, session=session)


@pytest.mark.asyncio
async def test_self_approval_blocked_for_approve_and_reject(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    with pytest.raises(SelfApprovalError):
        await ApprovalsService.approve(req.id, session=session, approver_user_id=requester.id)
    with pytest.raises(SelfApprovalError):
        await ApprovalsService.reject(req.id, session=session, approver_user_id=requester.id)
