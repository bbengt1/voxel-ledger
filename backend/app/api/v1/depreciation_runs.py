"""Depreciation-run operator endpoint (Phase 9.3, #155).

``POST /api/v1/depreciation-runs`` triggers the same flow as the monthly
worker for an arbitrary ``period_end`` so the operator can re-run a
missed month. Restricted to owner + bookkeeper.

The service commits per-entry internally; this endpoint does NOT call
``session.commit()`` afterward.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.depreciation_run import DepreciationRunRequest, DepreciationRunResponse
from app.services import depreciation_run as service

router = APIRouter(prefix="/depreciation-runs", tags=["fixed-assets"])

_WRITE_ROLES = ("owner", "bookkeeper")


@router.post(
    "",
    response_model=DepreciationRunResponse,
    status_code=status.HTTP_200_OK,
)
async def create_depreciation_run(
    payload: DepreciationRunRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> DepreciationRunResponse:
    try:
        result = await service.run_for_period(
            session=session,
            period_end=payload.period_end,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return DepreciationRunResponse(
        period_end=result.period_end,
        posted_count=result.posted_count,
        failed_count=result.failed_count,
    )
