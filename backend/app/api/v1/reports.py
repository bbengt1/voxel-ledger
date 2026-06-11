"""Reporting API (Phase 7.6, #114; trimmed in #318 Phase 5d).

QBO replace-mode (epic #312): the GL-backed financial reports (income
statement, balance sheet, cash flow, trial balance, GL detail, AR/AP aging,
budget variance, divisions comparison, tax liability) were removed — QuickBooks
is the system of record and its reporting replaces them. ``GET
/quickbooks-link`` is the generic link-out the frontend points at (phase-0
decision: no report deep-links; the Reports API is the only supported in-app
data path and is CorePlus-metered).

What remains is the *operational* reporting that never lived in the GL:
sales-by-period and inventory-valuation. JSON by default, CSV via
``?format=csv``.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.sales_inventory_reports import (
    InventoryValuationResponse,
    InventoryValuationRowResponse,
    SalesByPeriodResponse,
    SalesByPeriodRowResponse,
)
from app.services.reports import inventory_valuation as inventory_valuation_service
from app.services.reports import sales_by_period as sales_by_period_service

router = APIRouter(prefix="/reports", tags=["reports"])

_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")
_INVENTORY_READ_ROLES = ("owner", "bookkeeper", "production", "viewer")

# Generic QBO web-app entry point (phase-0 §link-out: no deep links).
_QBO_WEB_URL = "https://app.qbo.intuit.com"


class QuickBooksLinkResponse(BaseModel):
    url: str


@router.get("/quickbooks-link", response_model=QuickBooksLinkResponse)
async def quickbooks_link(
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> QuickBooksLinkResponse:
    """Where financial reporting lives now: the QBO web app (#318 Phase 5d)."""
    return QuickBooksLinkResponse(url=_QBO_WEB_URL)


@router.get("/sales-by-period", response_model=SalesByPeriodResponse)
async def sales_by_period_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    bucket: Annotated[str, Query()] = "month",
    channel_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await sales_by_period_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            bucket=bucket,  # type: ignore[arg-type]
            channel_id=channel_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = sales_by_period_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="sales-by-period.csv"',
            },
        )

    return SalesByPeriodResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        bucket=report.bucket,
        channel_id=uuid.UUID(report.channel_id) if report.channel_id else None,
        rows=[
            SalesByPeriodRowResponse(
                channel_id=uuid.UUID(r.channel_id),
                bucket_start=r.bucket_start,
                gross_sales=r.gross_sales,
                refunds=r.refunds,
                net_sales=r.net_sales,
                order_count=r.order_count,
            )
            for r in report.rows
        ],
        total_gross=report.total_gross,
        total_refunds=report.total_refunds,
        total_net=report.total_net,
        total_orders=report.total_orders,
    )  # type: ignore[return-value]


@router.get("/inventory-valuation", response_model=InventoryValuationResponse)
async def inventory_valuation_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_INVENTORY_READ_ROLES))],
    as_of: Annotated[date_type | None, Query()] = None,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    report = await inventory_valuation_service.build(session, as_of=as_of, location_id=location_id)

    if format == "csv":
        body = inventory_valuation_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="inventory-valuation.csv"',
            },
        )

    return InventoryValuationResponse(
        as_of=report.as_of,
        location_id=uuid.UUID(report.location_id) if report.location_id else None,
        rows=[
            InventoryValuationRowResponse(
                entity_kind=r.entity_kind,
                entity_id=uuid.UUID(r.entity_id),
                name=r.name,
                sku=r.sku,
                location_id=uuid.UUID(r.location_id),
                location_name=r.location_name,
                on_hand=r.on_hand,
                unit_cost=r.unit_cost,
                valuation=r.valuation,
            )
            for r in report.rows
        ],
        total_valuation=report.total_valuation,
        totals_by_kind=report.totals_by_kind,
        totals_by_location=report.totals_by_location,
    )  # type: ignore[return-value]
