"""Expense claims API (Phase 8.7, #134).

Thin layer over ``app.services.expense_claims``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role:

* write (create / update / submit / cancel): any logged-in user can
  submit their own claim. Submitters can only see/edit/cancel their own
  claim; owner + bookkeeper see all.
* approve / reject / mark-reimbursed: owner + bookkeeper only.

Self-approval guard: a submitter approving their own claim returns 403.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import Role, User
from app.models.expense_claim import ExpenseClaim, ExpenseClaimLine, ExpenseClaimState
from app.schemas.expense_claims import (
    ExpenseClaimApproveRequest,
    ExpenseClaimCreate,
    ExpenseClaimLineCreate,
    ExpenseClaimLineResponse,
    ExpenseClaimLineUpdate,
    ExpenseClaimListResponse,
    ExpenseClaimReimburseRequest,
    ExpenseClaimRejectRequest,
    ExpenseClaimResponse,
    ExpenseClaimSubmitResponse,
    ExpenseClaimUpdate,
)
from app.services import expense_claims as claims_service

router = APIRouter(prefix="/expense-claims", tags=["expense-claims"])


_PRIVILEGED_ROLES = {Role.OWNER.value, Role.BOOKKEEPER.value}


def _to_line(line: ExpenseClaimLine) -> ExpenseClaimLineResponse:
    return ExpenseClaimLineResponse(
        id=line.id,
        line_number=line.line_number,
        expense_category_id=line.expense_category_id,
        description=line.description,
        amount=line.amount,
        occurred_on=line.occurred_on,
        attachment_id=line.attachment_id,
        is_billable=line.is_billable,
        customer_id=line.customer_id,
        billed_invoice_item_id=line.billed_invoice_item_id,
        markup_percent=line.markup_percent,
    )


def _to_response(claim: ExpenseClaim) -> ExpenseClaimResponse:
    state_value = claim.state.value if isinstance(claim.state, ExpenseClaimState) else claim.state
    return ExpenseClaimResponse(
        id=claim.id,
        claim_number=claim.claim_number,
        submitter_user_id=claim.submitter_user_id,
        state=state_value,  # type: ignore[arg-type]
        submitted_at=claim.submitted_at,
        approved_at=claim.approved_at,
        approver_user_id=claim.approver_user_id,
        rejection_reason=claim.rejection_reason,
        total_amount=claim.total_amount,
        currency=claim.currency,
        posting_journal_entry_id=claim.posting_journal_entry_id,
        approval_request_id=claim.approval_request_id,
        reimbursement_payment_id=claim.reimbursement_payment_id,
        notes=claim.notes,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        lines=[_to_line(line) for line in sorted(claim.lines, key=lambda x: x.line_number)],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, claims_service.ExpenseClaimNotFoundError):
        return HTTPException(status_code=404, detail="expense claim not found")
    if isinstance(exc, claims_service.BillPaymentNotFoundForClaimError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, claims_service.MissingReimbursableAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, claims_service.ExpenseCategoryMissingAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, claims_service.InvalidExpenseClaimLineError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, claims_service.InvalidExpenseClaimStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, claims_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, claims_service.ExpenseClaimsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def _is_privileged(actor: User) -> bool:
    role = actor.role.value if hasattr(actor.role, "value") else actor.role
    return role in _PRIVILEGED_ROLES


def _check_visible(claim: ExpenseClaim, actor: User) -> None:
    if _is_privileged(actor):
        return
    if claim.submitter_user_id != actor.id:
        # Hide existence from non-privileged non-submitters.
        raise HTTPException(status_code=404, detail="expense claim not found")


def _check_writable(claim: ExpenseClaim, actor: User) -> None:
    if _is_privileged(actor):
        return
    if claim.submitter_user_id != actor.id:
        raise HTTPException(status_code=403, detail="forbidden")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=ExpenseClaimResponse, status_code=status.HTTP_201_CREATED)
async def create_expense_claim(
    payload: ExpenseClaimCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimResponse:
    # Viewer is read-only across the system; mirror /bills.
    role = actor.role.value if hasattr(actor.role, "value") else actor.role
    if role == Role.VIEWER.value:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        claim = await claims_service.create_draft(
            session,
            submitter_user_id=actor.id,
            lines=[line.model_dump() for line in payload.lines],
            notes=payload.notes,
            currency=payload.currency,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim.id)
    return _to_response(claim)


@router.get("", response_model=ExpenseClaimListResponse)
async def list_expense_claims(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
    submitter_user_id: Annotated[uuid.UUID | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ExpenseClaimListResponse:
    # Non-privileged callers only see their own claims.
    if not _is_privileged(actor):
        submitter_user_id = actor.id
    try:
        page = await claims_service.list_claims(
            session,
            submitter_user_id=submitter_user_id,
            state=state,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return ExpenseClaimListResponse(
        items=[_to_response(c) for c in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{claim_id}", response_model=ExpenseClaimResponse)
async def get_expense_claim(
    claim_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    _check_visible(claim, actor)
    return _to_response(claim)


@router.patch("/{claim_id}", response_model=ExpenseClaimResponse)
async def update_expense_claim(
    claim_id: uuid.UUID,
    payload: ExpenseClaimUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    _check_writable(claim, actor)
    patch_dict = payload.model_dump(exclude_unset=True)
    if "lines" in patch_dict and patch_dict["lines"] is not None:
        patch_dict["lines"] = [
            line.model_dump() if hasattr(line, "model_dump") else dict(line)
            for line in patch_dict["lines"]
        ]
    try:
        await claims_service.update_draft(
            session, claim_id=claim_id, patch=patch_dict, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


@router.post("/{claim_id}/submit", response_model=ExpenseClaimSubmitResponse)
async def submit_expense_claim(
    claim_id: uuid.UUID,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimSubmitResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    _check_writable(claim, actor)
    try:
        claim = await claims_service.submit(session, claim_id=claim_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    if claim.approval_request_id is not None:
        response.status_code = status.HTTP_202_ACCEPTED
    return ExpenseClaimSubmitResponse(
        claim=_to_response(claim),
        approval_request_id=claim.approval_request_id,
    )


@router.post("/{claim_id}/approve", response_model=ExpenseClaimResponse)
async def approve_expense_claim(
    claim_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    payload: ExpenseClaimApproveRequest | None = None,
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    if claim.submitter_user_id == actor.id:
        raise HTTPException(status_code=403, detail="cannot approve your own expense claim")
    try:
        await claims_service.approve(
            session,
            claim_id=claim_id,
            actor_user_id=actor.id,
            decision_note=payload.note if payload else None,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)


@router.post("/{claim_id}/reject", response_model=ExpenseClaimResponse)
async def reject_expense_claim(
    claim_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    payload: ExpenseClaimRejectRequest | None = None,
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    if claim.submitter_user_id == actor.id:
        raise HTTPException(status_code=403, detail="cannot reject your own expense claim")
    try:
        await claims_service.reject(
            session,
            claim_id=claim_id,
            actor_user_id=actor.id,
            rejection_reason=payload.rejection_reason if payload else None,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)


@router.post("/{claim_id}/cancel", response_model=ExpenseClaimResponse)
async def cancel_expense_claim(
    claim_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    _check_writable(claim, actor)
    try:
        await claims_service.cancel(session, claim_id=claim_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)


@router.post("/{claim_id}/mark-reimbursed", response_model=ExpenseClaimResponse)
async def mark_reimbursed_expense_claim(
    claim_id: uuid.UUID,
    payload: ExpenseClaimReimburseRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> ExpenseClaimResponse:
    try:
        await claims_service.mark_reimbursed(
            session,
            claim_id=claim_id,
            bill_payment_id=payload.bill_payment_id,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)


# ---------------------------------------------------------------------------
# Line CRUD (draft only)
# ---------------------------------------------------------------------------


@router.post(
    "/{claim_id}/lines",
    response_model=ExpenseClaimResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_expense_claim_line(
    claim_id: uuid.UUID,
    payload: ExpenseClaimLineCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    _check_writable(claim, actor)
    try:
        await claims_service.add_line(
            session,
            claim_id=claim_id,
            line=payload.model_dump(),
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)


@router.patch("/{claim_id}/lines/{line_id}", response_model=ExpenseClaimResponse)
async def update_expense_claim_line(
    claim_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: ExpenseClaimLineUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    _check_writable(claim, actor)
    try:
        await claims_service.update_line(
            session,
            claim_id=claim_id,
            line_id=line_id,
            patch=payload.model_dump(exclude_unset=True),
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)


@router.delete("/{claim_id}/lines/{line_id}", response_model=ExpenseClaimResponse)
async def delete_expense_claim_line(
    claim_id: uuid.UUID,
    line_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> ExpenseClaimResponse:
    try:
        claim = await claims_service.get(session, claim_id)
    except Exception as exc:
        raise _map_error(exc) from None
    _check_writable(claim, actor)
    try:
        await claims_service.delete_line(
            session,
            claim_id=claim_id,
            line_id=line_id,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    claim = await claims_service.get(session, claim_id)
    return _to_response(claim)
