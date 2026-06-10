"""Admin endpoints for QBO reconciliation + CDC drift (#317 Phase 4b/4c).

Owner-only, mounted under ``/api/v1/admin/quickbooks``:

* ``GET  /reconciliation?from&to`` → completeness report + decommission-ready gate.
* ``GET  /drift``                  → CDC drift rows (filter by status, paged).
* ``POST /drift/{id}/acknowledge`` → mark a drift row reviewed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.qbo_cdc_drift import QboDriftStatus
from app.services.quickbooks import cdc, monitoring, reconcile

router = APIRouter(prefix="/quickbooks", tags=["admin-quickbooks"])

_DEFAULT_RANGE_DAYS = 90
_MAX_PAGE = 200


class GapItemResponse(BaseModel):
    kind: str
    local_id: uuid.UUID
    reference: str | None = None
    occurred_at: datetime | None = None


class DriftItemResponse(BaseModel):
    entity_type: str
    qbo_id: str
    change_type: str
    local_kind: str | None = None
    local_id: uuid.UUID | None = None
    occurrences: int
    last_detected_at: datetime


class WorkerHealthResponse(BaseModel):
    job_name: str
    last_finished_at: datetime | None = None
    last_status: str | None = None
    last_duration_ms: int | None = None
    last_processed: int = 0


class SyncMetricsResponse(BaseModel):
    enabled: bool
    connected: bool
    outbox: dict[str, int]
    drift_open: int
    oldest_pending_age_seconds: int | None = None
    sync_worker: WorkerHealthResponse
    cdc_worker: WorkerHealthResponse


class ReconciliationResponse(BaseModel):
    date_from: date
    date_to: date
    outbox: dict[str, int]
    gaps: list[GapItemResponse]
    gap_count: int
    drift: list[DriftItemResponse]
    drift_open: int
    mismatch_candidates: int
    decommission_ready: bool


class DriftRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    qbo_id: str
    change_type: str
    local_kind: str | None = None
    local_id: uuid.UUID | None = None
    occurrences: int
    status: str
    detail: dict | None = None
    first_detected_at: datetime
    last_detected_at: datetime
    acknowledged_at: datetime | None = None


class DriftListResponse(BaseModel):
    items: list[DriftRowResponse]
    next_cursor: str | None = None


@router.get("/metrics", response_model=SyncMetricsResponse)
async def get_metrics(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> SyncMetricsResponse:
    m = await monitoring.build_metrics(session)
    return SyncMetricsResponse(
        enabled=m.enabled,
        connected=m.connected,
        outbox=m.outbox,
        drift_open=m.drift_open,
        oldest_pending_age_seconds=m.oldest_pending_age_seconds,
        sync_worker=WorkerHealthResponse(**vars(m.sync_worker)),
        cdc_worker=WorkerHealthResponse(**vars(m.cdc_worker)),
    )


@router.get("/reconciliation", response_model=ReconciliationResponse)
async def get_reconciliation(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> ReconciliationResponse:
    today = datetime.now(UTC).date()
    to_d = date_to or today
    from_d = date_from or (to_d - timedelta(days=_DEFAULT_RANGE_DAYS))
    if from_d > to_d:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="'from' must be on/before 'to'")
    report = await reconcile.build(session, date_from=from_d, date_to=to_d)
    return ReconciliationResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        outbox=report.outbox,
        gaps=[
            GapItemResponse(
                kind=g.kind, local_id=g.local_id, reference=g.reference, occurred_at=g.occurred_at
            )
            for g in report.gaps
        ],
        gap_count=report.gap_count,
        drift=[
            DriftItemResponse(
                entity_type=d.entity_type,
                qbo_id=d.qbo_id,
                change_type=d.change_type,
                local_kind=d.local_kind,
                local_id=d.local_id,
                occurrences=d.occurrences,
                last_detected_at=d.last_detected_at,
            )
            for d in report.drift
        ],
        drift_open=report.drift_open,
        mismatch_candidates=report.mismatch_candidates,
        decommission_ready=report.decommission_ready,
    )


@router.get("/drift", response_model=DriftListResponse)
async def list_drift(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    cursor: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = 100,
) -> DriftListResponse:
    if status_filter is not None and status_filter not in {s.value for s in QboDriftStatus}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"unknown status {status_filter!r}")
    rows = await cdc.list_drift(session, status=status_filter, limit=limit, before=cursor)
    next_cursor = rows[-1].last_detected_at.isoformat() if len(rows) == limit else None
    return DriftListResponse(
        items=[DriftRowResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


@router.post("/drift/{drift_id}/acknowledge", response_model=DriftRowResponse)
async def acknowledge_drift(
    drift_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> DriftRowResponse:
    try:
        row = await cdc.acknowledge_drift(session, drift_id, actor_user_id=user.id)
    except cdc.DriftNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    resp = DriftRowResponse.model_validate(row)
    await session.commit()
    return resp
