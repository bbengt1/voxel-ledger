"""Late-fee-policies API (Phase 7.6, #114).

Thin layer over ``app.services.late_fee_policies``. Owner + bookkeeper
write; same plus sales/viewer read. The ``/apply-now`` endpoint runs
the daily-worker entrypoint synchronously for ops triggering.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.late_fee_policy import LateFeeKind, LateFeePolicy
from app.schemas.late_fee_policies import (
    LateFeeApplyResponse,
    LateFeePolicyCreate,
    LateFeePolicyListResponse,
    LateFeePolicyResponse,
    LateFeePolicyUpdate,
)
from app.services import late_fee_policies as policy_service
from app.services import late_fees as late_fees_service

router = APIRouter(prefix="/late-fee-policies", tags=["late-fee-policies"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_response(p: LateFeePolicy) -> LateFeePolicyResponse:
    return LateFeePolicyResponse(
        id=p.id,
        customer_id=p.customer_id,
        kind=(p.kind.value if isinstance(p.kind, LateFeeKind) else p.kind),  # type: ignore[arg-type]
        amount=p.amount,
        grace_period_days=p.grace_period_days,
        apply_after_days=p.apply_after_days,
        compound_interval_days=p.compound_interval_days,
        is_active=p.is_active,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, policy_service.LateFeePolicyNotFoundError):
        return HTTPException(status_code=404, detail="late-fee policy not found")
    if isinstance(exc, policy_service.InvalidLateFeePolicyError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, policy_service.LateFeePolicyServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=LateFeePolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: LateFeePolicyCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> LateFeePolicyResponse:
    try:
        policy = await policy_service.create(
            session,
            customer_id=payload.customer_id,
            kind=payload.kind,
            amount=payload.amount,
            grace_period_days=payload.grace_period_days,
            apply_after_days=payload.apply_after_days,
            compound_interval_days=payload.compound_interval_days,
            is_active=payload.is_active,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    policy = await policy_service.get(session, policy.id)
    return _to_response(policy)


@router.get("", response_model=LateFeePolicyListResponse)
async def list_policies(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    include_inactive: bool = False,
) -> LateFeePolicyListResponse:
    items = await policy_service.list_policies(session, include_inactive=include_inactive)
    return LateFeePolicyListResponse(items=[_to_response(p) for p in items])


@router.get("/{policy_id}", response_model=LateFeePolicyResponse)
async def get_policy(
    policy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> LateFeePolicyResponse:
    try:
        policy = await policy_service.get(session, policy_id)
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
    patch_dict = payload.model_dump(exclude_unset=True)
    try:
        policy = await policy_service.update(
            session,
            policy_id=policy_id,
            actor_user_id=actor.id,
            **patch_dict,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    policy = await policy_service.get(session, policy.id)
    return _to_response(policy)


@router.delete("/{policy_id}", response_model=LateFeePolicyResponse)
async def deactivate_policy(
    policy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> LateFeePolicyResponse:
    try:
        policy = await policy_service.deactivate(
            session, policy_id=policy_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    policy = await policy_service.get(session, policy.id)
    return _to_response(policy)


@router.post("/apply-now", response_model=LateFeeApplyResponse)
async def apply_now(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> LateFeeApplyResponse:
    """Operator-triggered run of the late-fees worker.

    Also runs the overdue marker first so a missed daily run can catch
    up in a single ops click.
    """
    try:
        now = datetime.now(UTC)
        await late_fees_service.mark_overdue_invoices(
            session=session, now=now, actor_user_id=actor.id
        )
        result = await late_fees_service.apply_late_fees(
            session=session, now=now, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"apply-now failed: {exc}") from None
    await session.commit()
    return LateFeeApplyResponse(
        applied=result.applied,
        skipped=result.skipped,
        deferred=result.deferred,
        fees_total=result.fees_total,
    )
