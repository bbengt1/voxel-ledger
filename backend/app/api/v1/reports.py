"""Reporting API (Phase 7.6, #114).

Currently exposes the AR aging report. JSON by default, CSV via
``?format=csv``.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
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
from app.schemas.income_statement import (
    IncomeStatementResponse,
    IncomeStatementRowResponse,
)
from app.schemas.late_fees import (
    AgingBucketResponse,
    AgingRowResponse,
    ArAgingReportResponse,
)
from app.schemas.tax_remittances import (
    TaxLiabilityReportResponse,
    TaxLiabilityRowResponse,
)
from app.services.reports import ap_aging as ap_aging_service
from app.services.reports import ar_aging as ar_aging_service
from app.services.reports import income_statement as income_statement_service
from app.services.reports import tax_liability as tax_liability_service

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


@router.get("/tax-liability", response_model=TaxLiabilityReportResponse)
async def tax_liability_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    profile_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await tax_liability_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            profile_id=str(profile_id) if profile_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = tax_liability_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="tax-liability.csv"'},
        )

    return TaxLiabilityReportResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        rows=[
            TaxLiabilityRowResponse(
                profile_id=uuid.UUID(row.profile_id),
                profile_code=row.profile_code,
                profile_name=row.profile_name,
                jurisdiction=row.jurisdiction,
                rate_id=uuid.UUID(row.rate_id),
                rate_name=row.rate_name,
                rate=row.rate,
                compound_on_previous=row.compound_on_previous,
                tax_collected=row.tax_collected,
                tax_remitted=row.tax_remitted,
                net_liability=row.net_liability,
                gross_taxable_sales=row.gross_taxable_sales,
            )
            for row in report.rows
        ],
        grand_total_collected=report.grand_total_collected,
        grand_total_remitted=report.grand_total_remitted,
        grand_total_net=report.grand_total_net,
    )  # type: ignore[return-value]


@router.get("/income-statement", response_model=IncomeStatementResponse)
async def income_statement_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    division_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await income_statement_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            division_id=division_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = income_statement_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="income-statement.csv"',
            },
        )

    def _to_rows(rows):
        return [
            IncomeStatementRowResponse(
                account_id=uuid.UUID(r.account_id),
                code=r.code,
                name=r.name,
                depth=r.depth,
                section=r.section,
                amount=r.amount,
            )
            for r in rows
        ]

    return IncomeStatementResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        division_id=uuid.UUID(report.division_id) if report.division_id else None,
        revenue_rows=_to_rows(report.revenue_rows),
        cogs_rows=_to_rows(report.cogs_rows),
        operating_expense_rows=_to_rows(report.operating_expense_rows),
        total_revenue=report.total_revenue,
        total_cogs=report.total_cogs,
        gross_profit=report.gross_profit,
        total_operating_expenses=report.total_operating_expenses,
        operating_income=report.operating_income,
        net_income=report.net_income,
    )  # type: ignore[return-value]
