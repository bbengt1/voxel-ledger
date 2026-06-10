"""Admin endpoints for the QBO sync outbox (#316 Phase 3e, epic #312).

Owner-only, mounted under ``/api/v1/admin/quickbooks``. Lets an operator watch
the outbox the ``quickbooks_sync`` worker drains and recover from terminal-error
rows:

* ``GET  /outbox/stats``           → counts by status (pending/synced/failed/dead).
* ``GET  /outbox``                 → most-recent-first page of rows (+ filters).
* ``POST /outbox/{row_id}/retry``  → requeue one failed/dead row.
* ``POST /outbox/retry``           → bulk-requeue every failed (or dead) row.

Retry resets the row to ``pending`` for the next worker pass; the stable
``request_id`` keeps the repush idempotent in QBO.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.qbo_sync_outbox import QboSyncStatus
from app.services.quickbooks import outbox

router = APIRouter(prefix="/quickbooks", tags=["admin-quickbooks"])

_DEFAULT_PAGE = 50
_MAX_PAGE = 200


class OutboxStatsResponse(BaseModel):
    pending: int
    synced: int
    failed: int
    dead: int
    total: int


class OutboxRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    local_id: uuid.UUID
    op: str
    status: str
    attempts: int
    qbo_entity_type: str | None = None
    qbo_id: str | None = None
    last_error: str | None = None
    next_attempt_at: datetime
    created_at: datetime
    updated_at: datetime


class OutboxListResponse(BaseModel):
    items: list[OutboxRowResponse]
    next_cursor: str | None = None


class RetryAllRequest(BaseModel):
    status: str  # "failed" | "dead"


class RetryAllResponse(BaseModel):
    requeued: int


@router.get("/outbox/stats", response_model=OutboxStatsResponse)
async def outbox_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> OutboxStatsResponse:
    counts = await outbox.stats(session)
    return OutboxStatsResponse(**counts)


@router.get("/outbox", response_model=OutboxListResponse)
async def list_outbox(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    kind: Annotated[str | None, Query()] = None,
    cursor: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = _DEFAULT_PAGE,
) -> OutboxListResponse:
    if status_filter is not None and status_filter not in {s.value for s in QboSyncStatus}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"unknown status {status_filter!r}")
    rows = await outbox.list_rows(
        session, status=status_filter, kind=kind, limit=limit, before=cursor
    )
    next_cursor = rows[-1].created_at.isoformat() if len(rows) == limit else None
    return OutboxListResponse(
        items=[OutboxRowResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post("/outbox/{row_id}/retry", response_model=OutboxRowResponse)
async def retry_outbox_row(
    row_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> OutboxRowResponse:
    try:
        row = await outbox.retry_row(session, row_id)
    except outbox.OutboxRowNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except outbox.OutboxNotRetryableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    # Serialize while the row's attributes are still loaded (commit expires them).
    resp = OutboxRowResponse.model_validate(row)
    await session.commit()
    return resp


@router.post("/outbox/retry", response_model=RetryAllResponse)
async def retry_all_outbox(
    body: RetryAllRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> RetryAllResponse:
    try:
        n = await outbox.retry_all(session, status=body.status)
    except outbox.OutboxNotRetryableError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    return RetryAllResponse(requeued=n)
