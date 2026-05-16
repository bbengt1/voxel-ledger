"""Reporting API (Phase 7.6, #114).

Currently exposes the AR aging report. JSON by default, CSV via
``?format=csv``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.ap_aging import (
    ApAgingBucketResponse,
    ApAgingReportResponse,
    ApAgingRowResponse,
)
from app.schemas.late_fees import (
    AgingBucketResponse,
    AgingRowResponse,
    ArAgingReportResponse,
)
from app.services.reports import ap_aging as ap_aging_service
from app.services.reports import ar_aging as ar_aging_service

router = APIRouter(prefix="/reports", tags=["reports"])

_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _parse_buckets(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        cuts = [int(p) for p in parts]
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="buckets must be a comma-separated list of integers (e.g. 30,60,90)",
        ) from exc
    if any(c <= 0 for c in cuts):
        raise HTTPException(status_code=400, detail="bucket cut points must be > 0")
    return cuts


@router.get("/ar-aging", response_model=ArAgingReportResponse)
async def ar_aging_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    buckets: Annotated[str | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    cuts = _parse_buckets(buckets)
    report = await ar_aging_service.build(session, buckets=cuts)

    if format == "csv":
        body = ar_aging_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ar-aging.csv"'},
        )

    return ArAgingReportResponse(
        as_of=report.as_of,
        bucket_labels=report.bucket_labels,
        rows=[
            AgingRowResponse(
                customer_id=row.customer_id,
                customer_number=row.customer_number,
                display_name=row.display_name,
                total_outstanding=row.total_outstanding,
                buckets=[AgingBucketResponse(label=b.label, amount=b.amount) for b in row.buckets],
            )
            for row in report.rows
        ],
        grand_total=report.grand_total,
        grand_total_by_bucket=report.grand_total_by_bucket,
    )  # type: ignore[return-value]


@router.get("/ap-aging", response_model=ApAgingReportResponse)
async def ap_aging_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    buckets: Annotated[str | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    cuts = _parse_buckets(buckets)
    report = await ap_aging_service.build(session, buckets=cuts)

    if format == "csv":
        body = ap_aging_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ap-aging.csv"'},
        )

    return ApAgingReportResponse(
        as_of=report.as_of,
        bucket_labels=report.bucket_labels,
        rows=[
            ApAgingRowResponse(
                vendor_id=row.vendor_id,
                vendor_number=row.vendor_number,
                display_name=row.display_name,
                total_outstanding=row.total_outstanding,
                buckets=[
                    ApAgingBucketResponse(label=b.label, amount=b.amount) for b in row.buckets
                ],
            )
            for row in report.rows
        ],
        grand_total=report.grand_total,
        grand_total_by_bucket=report.grand_total_by_bucket,
    )  # type: ignore[return-value]
