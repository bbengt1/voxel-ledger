"""Late-fee-policies API + operator-triggered apply-now (Phase 7.6, #114)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.late_fee_policy import LateFeeKind, LateFeePolicy
from app.schemas.late_fees import (
    LateFeeApplyNowResponse,
    LateFeeApplyNowResult,
    LateFeePolicyCreate,
    LateFeePolicyListResponse,
    LateFeePolicyResponse,
    LateFeePolicyUpdate,
)
from app.services import late_fees as service

router = APIRouter(prefix="/late-fee-policies", tags=["late-fee-policies"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_response(p: LateFeePolicy) -> LateFeePolicyResponse:
    return LateFeePolicyResponse(
        id=p.id,
        customer_id=p.customer_id,
        kind=p.kind.value if isinstance(p.kind, LateFeeKind) else p.kind,  # type: ignore[arg-type]
        amount=p.amount,
        grace_period_days=p.grace_period_days,
        apply_after_days=p.apply_after_days,
        compound_interval_days=p.compound_interval_days,
        is_active=p.is_active,
        notes=p.notes,
        created_by_user_id=p.created_by_user_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, service.LateFeePolicyNotFoundError):
        return HTTPException(status_code=404, detail="late-fee policy not found")
    if isinstance(exc, service.InvalidLateFeePolicyError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, service.LateFeesServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=LateFeePolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: LateFeePolicyCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> LateFeePolicyResponse:
    try:
        policy = await service.create_policy(
            session,
            kind=payload.kind,
            amount=payload.amount,
            customer_id=payload.customer_id,
            grace_period_days=payload.grace_period_days,
            apply_after_days=payload.apply_after_days,
            compound_interval_days=payload.compound_interval_days,
            is_active=payload.is_active,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    policy = await service.get_policy(session, policy.id)
    return _to_response(policy)


@router.get("", response_model=LateFeePolicyListResponse)
async def list_policies(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> LateFeePolicyListResponse:
    policies = await service.list_policies(
        session,
        customer_id=customer_id,
        include_inactive=include_inactive,
        limit=limit,
    )
    return LateFeePolicyListResponse(items=[_to_response(p) for p in policies])


@router.get("/{policy_id}", response_model=LateFeePolicyResponse)
async def get_policy(
    policy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> LateFeePolicyResponse:
    try:
        policy = await service.get_policy(session, policy_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(policy)


@router.patch("/{policy_id}", response_model=LateFeePolicyResponse)
async def update_policy(
    policy_id: uuid.UUID,
    payload: LateFeePolicyUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> LateFeePolicyResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        await service.update_policy(
            session, policy_id=policy_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    policy = await service.get_policy(session, policy_id)
    return _to_response(policy)


@router.post("/{policy_id}/deactivate", response_model=LateFeePolicyResponse)
async def deactivate_policy(
    policy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> LateFeePolicyResponse:
    try:
        await service.deactivate_policy(session, policy_id=policy_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    policy = await service.get_policy(session, policy_id)
    return _to_response(policy)


@router.post("/apply-now", response_model=LateFeeApplyNowResponse)
async def apply_now(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> LateFeeApplyNowResponse:
    """Operator-triggered sweep: mark overdue, then apply fees."""
    try:
        await service.mark_overdue(session=session, actor_user_id=actor.id)
        results = await service.apply_late_fees(session=session, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return LateFeeApplyNowResponse(
        applied=[
            LateFeeApplyNowResult(
                invoice_id=r.invoice_id,
                policy_id=r.policy_id,
                debit_note_id=r.debit_note_id,
                amount=r.amount,
            )
            for r in results
        ]
    )
