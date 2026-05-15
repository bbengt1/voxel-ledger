"""Approval-workflow endpoints (Phase 4.4, #67).

Thin layer over :class:`ApprovalsService`. Role gating per route:

- Create / list / read: any authenticated role for their own requests;
  owner and bookkeeper see everything.
- Approve / reject: owner or bookkeeper only. The self-approval guard
  in the service still rejects a requester who somehow also sits in the
  approver role-set.
- Cancel: requester themselves, or owner.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import Role, User
from app.schemas.approvals import (
    ApprovalActionRequest,
    ApprovalCancelRequest,
    ApprovalRequestListResponse,
    ApprovalRequestResponse,
)
from app.services.approvals import (
    ApprovalAlreadyDecidedError,
    ApprovalCancelForbiddenError,
    ApprovalRequestNotFoundError,
    ApprovalsService,
    ApprovalsServiceError,
    InvalidCursorError,
    SelfApprovalError,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


_ADMIN_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.BOOKKEEPER})


def _is_admin(user: User) -> bool:
    return user.role in _ADMIN_ROLES


def _map_service_error(exc: ApprovalsServiceError) -> HTTPException:
    if isinstance(exc, ApprovalRequestNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="approval request not found",
        )
    if isinstance(
        exc,
        ApprovalAlreadyDecidedError
        | SelfApprovalError
        | ApprovalCancelForbiddenError
        | InvalidCursorError,
    ):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _to_response(row) -> ApprovalRequestResponse:  # type: ignore[no-untyped-def]
    # Read attributes explicitly so we don't trip a lazy-load on
    # ``updated_at`` (server-default + onupdate) right after a mutation
    # in an async session.
    return ApprovalRequestResponse(
        id=row.id,
        request_type=row.request_type,
        subject_kind=row.subject_kind,
        subject_id=row.subject_id,
        requested_by_user_id=row.requested_by_user_id,
        requested_at=row.requested_at,
        state=row.state,
        decided_by_user_id=row.decided_by_user_id,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
        payload=row.payload,
        threshold_amount=row.threshold_amount,
        consumed_at=row.consumed_at,
        created_at=row.created_at,
        updated_at=row.updated_at or row.created_at,
    )


@router.get("", response_model=ApprovalRequestListResponse)
async def list_approvals(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
    state: Annotated[str | None, Query()] = None,
    request_type: Annotated[str | None, Query()] = None,
    subject_kind: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ApprovalRequestListResponse:
    """List approval requests.

    Admin roles (owner, bookkeeper) see all rows. Other roles see only
    their own requests — the service scopes the query by
    ``requested_by_user_id``.
    """
    requested_by = None if _is_admin(actor) else actor.id
    try:
        page = await ApprovalsService.list(
            session=session,
            state=state,
            request_type=request_type,
            subject_kind=subject_kind,
            requested_by_user_id=requested_by,
            cursor=cursor,
            limit=limit,
        )
    except ApprovalsServiceError as exc:
        raise _map_service_error(exc) from None
    return ApprovalRequestListResponse(
        items=[_to_response(r) for r in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{request_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    request_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ApprovalRequestResponse:
    try:
        row = await ApprovalsService.get(request_id, session=session)
    except ApprovalsServiceError as exc:
        raise _map_service_error(exc) from None
    if not _is_admin(actor) and row.requested_by_user_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not allowed to view this approval request",
        )
    return _to_response(row)


@router.post(
    "/{request_id}/approve",
    response_model=ApprovalRequestResponse,
)
async def approve(
    request_id: uuid.UUID,
    payload: ApprovalActionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> ApprovalRequestResponse:
    try:
        row = await ApprovalsService.approve(
            request_id,
            session=session,
            approver_user_id=actor.id,
            decision_note=payload.decision_note,
        )
    except ApprovalsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    response = _to_response(row)
    await session.commit()
    return response


@router.post(
    "/{request_id}/reject",
    response_model=ApprovalRequestResponse,
)
async def reject(
    request_id: uuid.UUID,
    payload: ApprovalActionRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> ApprovalRequestResponse:
    try:
        row = await ApprovalsService.reject(
            request_id,
            session=session,
            approver_user_id=actor.id,
            decision_note=payload.decision_note,
        )
    except ApprovalsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    response = _to_response(row)
    await session.commit()
    return response


@router.post(
    "/{request_id}/cancel",
    response_model=ApprovalRequestResponse,
)
async def cancel(
    request_id: uuid.UUID,
    payload: ApprovalCancelRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ApprovalRequestResponse:
    """Cancel a pending request.

    Allowed for the original requester or an owner. The endpoint passes
    ``actor_is_owner`` to the service rather than letting the service
    re-query user roles.
    """
    try:
        row = await ApprovalsService.cancel(
            request_id,
            session=session,
            actor_user_id=actor.id,
            actor_is_owner=(actor.role == Role.OWNER),
            reason=payload.reason,
        )
    except ApprovalsServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    response = _to_response(row)
    await session.commit()
    return response
