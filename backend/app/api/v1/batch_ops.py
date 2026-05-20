"""Batch operations API (Phase 11.3, #195).

Preview is read-only; commit applies in a single transaction and
emits one ``batch_ops.BatchCommitted`` event so the audit projection
materializes a single audit_log row containing the affected IDs.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.batch_ops import (
    BatchCommitResponse,
    BatchPreviewResponse,
    BatchSpec,
    BlockerResponse,
)
from app.services import batch_ops as service

router = APIRouter(prefix="/batch", tags=["batch"])

_BATCH_ROLES = ("owner", "bookkeeper")


def _blocker_to_resp(b: service.Blocker) -> BlockerResponse:
    return BlockerResponse(id=b.id, reason=b.reason)


@router.post("/preview", response_model=BatchPreviewResponse)
async def preview(
    payload: BatchSpec,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_BATCH_ROLES))],
) -> BatchPreviewResponse:
    try:
        result = await service.preview(
            session=session,
            entity=payload.entity,
            ids=list(payload.ids),
            action=payload.action,
            params=dict(payload.params),
        )
    except service.BatchOpsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return BatchPreviewResponse(
        entity=result.entity,
        action=result.action,
        matched_count=result.matched_count,
        sample=result.sample,
        blockers=[_blocker_to_resp(b) for b in result.blockers],
    )


@router.post("/commit", response_model=BatchCommitResponse)
async def commit(
    payload: BatchSpec,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_BATCH_ROLES))],
) -> BatchCommitResponse:
    try:
        result = await service.commit(
            session=session,
            entity=payload.entity,
            ids=list(payload.ids),
            action=payload.action,
            actor_user_id=actor.id,
            params=dict(payload.params),
        )
    except service.BatchOpsError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    response = BatchCommitResponse(
        entity=result.entity,
        action=result.action,
        applied=result.applied,
        skipped=result.skipped,
        audit_id=result.audit_id,
        blockers=[_blocker_to_resp(b) for b in result.blockers],
    )
    await session.commit()
    return response
