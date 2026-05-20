"""Dashboard API (Phase 10.6, #181).

One endpoint for now: ``GET /api/v1/dashboard/kpis``. Future
``/dashboard/ai-insights/*`` endpoints land with Phase 10.7 (#182).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.dashboard import DashboardKpisResponse
from app.services.reports import dashboard_kpis as kpi_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


@router.get("/kpis", response_model=DashboardKpisResponse)
async def dashboard_kpis(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> DashboardKpisResponse:
    kpis = await kpi_service.build(session)
    return DashboardKpisResponse(
        as_of=kpis.as_of,
        cash_on_hand=kpis.cash_on_hand,
        accounts_receivable=kpis.accounts_receivable,
        accounts_payable=kpis.accounts_payable,
        overdue_invoice_count=kpis.overdue_invoice_count,
        overdue_bill_count=kpis.overdue_bill_count,
        low_stock_alert_count=kpis.low_stock_alert_count,
        net_income_mtd=kpis.net_income_mtd,
        net_income_ytd=kpis.net_income_ytd,
        last_updated_at=kpis.last_updated_at,
    )
