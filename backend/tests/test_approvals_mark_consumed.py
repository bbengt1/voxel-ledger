"""Direct unit coverage for ``ApprovalsService.mark_consumed`` (Phase 4.4)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.approvals import (
    ApprovalAlreadyConsumedError,
    ApprovalNotApprovedError,
    ApprovalsService,
)
from sqlalchemy.ext.asyncio import AsyncSession

from tests._approvals_helpers import make_pending, seed_user
from tests._je_helpers import ensure_schema


@pytest.mark.asyncio
async def test_pending_cannot_be_consumed(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    with pytest.raises(ApprovalNotApprovedError):
        await ApprovalsService.mark_consumed(req.id, session=session)


@pytest.mark.asyncio
async def test_rejected_cannot_be_consumed(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    await ApprovalsService.reject(req.id, session=session, approver_user_id=approver.id)
    with pytest.raises(ApprovalNotApprovedError):
        await ApprovalsService.mark_consumed(req.id, session=session)


@pytest.mark.asyncio
async def test_consume_then_consume_again_fails(session: AsyncSession, engine) -> None:
    await ensure_schema(engine)
    requester = await seed_user(session, email="r@x.com", role=Role.OWNER)
    approver = await seed_user(session, email="a@x.com", role=Role.OWNER)
    req = await make_pending(session, requester=requester)
    await ApprovalsService.approve(req.id, session=session, approver_user_id=approver.id)
    consumed = await ApprovalsService.mark_consumed(req.id, session=session)
    assert consumed.consumed_at is not None
    with pytest.raises(ApprovalAlreadyConsumedError):
        await ApprovalsService.mark_consumed(req.id, session=session)
