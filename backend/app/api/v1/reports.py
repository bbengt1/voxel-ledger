"""Reports API (Phase 7.6, #114).

Read-only aggregations. Today exposes ``GET /reports/ar-aging`` with
optional CSV export.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.late_fee_policies import (
    AgingBucketAmountSchema,
    ArAgingReportResponse,
    CustomerAgingRowSchema,
)
from app.services.reports import ar_aging as ar_aging_service
from app.services.settings.service import SettingsService

router = APIRouter(prefix="/reports", tags=["reports"])

_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _row_to_schema(row: ar_aging_service.CustomerAgingRow) -> CustomerAgingRowSchema:
    return CustomerAgingRowSchema(
        customer_id=uuid.UUID(row.customer_id),
        customer_number=row.customer_number,
        display_name=row.display_name,
        total_outstanding=row.total_outstanding,
        buckets=[
            AgingBucketAmountSchema(label=b.label, lower=b.lower, upper=b.upper, amount=b.amount)
            for b in row.buckets
        ],
    )


@router.get("/ar-aging")
async def ar_aging(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    buckets: Annotated[str | None, Query()] = None,
    as_of: Annotated[datetime | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
):
    default = await SettingsService.get("ar.aging_bucket_days", session=session)
    if not isinstance(default, list) or not default:
        default = [30, 60, 90]
    try:
        bucket_days = ar_aging_service.parse_bucket_query(buckets, default)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    report = await ar_aging_service.build_ar_aging(
        session=session, as_of=as_of, bucket_days=bucket_days
    )

    if format == "csv":
        csv_text = ar_aging_service.render_csv(report)
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ar-aging.csv"'},
        )

    return ArAgingReportResponse(
        as_of=report.as_of,
        bucket_days=report.bucket_days,
        rows=[_row_to_schema(r) for r in report.rows],
        grand_total=report.grand_total,
        grand_total_buckets=[
            AgingBucketAmountSchema(label=b.label, lower=b.lower, upper=b.upper, amount=b.amount)
            for b in report.grand_total_buckets
        ],
    )
