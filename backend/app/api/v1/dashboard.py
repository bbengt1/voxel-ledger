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


# ---------------------------------------------------------------------------
# AI insights (Phase 10.7, #182)
# ---------------------------------------------------------------------------

from fastapi import HTTPException, Query, status  # noqa: E402

from app.schemas.ai_insights import (  # noqa: E402
    AiInsightRequest,
    AiInsightSummaryResponse,
)
from app.services import ai_insights as insights_service  # noqa: E402

_INSIGHTS_WRITE_ROLES = ("owner", "bookkeeper")


def _insights_to_response(row) -> AiInsightSummaryResponse:
    return AiInsightSummaryResponse(
        id=row.id,
        scope=row.scope,
        period_start=row.period_start,
        period_end=row.period_end,
        payload=row.payload or {},
        narrative=row.narrative or "",
        model=row.model,
        status=row.status.value if hasattr(row.status, "value") else row.status,  # type: ignore[arg-type]
        error=row.error,
        requested_by_user_id=row.requested_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post(
    "/ai-insights/requests",
    response_model=AiInsightSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_ai_insight(
    payload: AiInsightRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_INSIGHTS_WRITE_ROLES))],
) -> AiInsightSummaryResponse:
    try:
        row = await insights_service.request(
            session=session,
            scope=payload.scope,
            period_start=payload.period_start,
            period_end=payload.period_end,
            actor_user_id=actor.id,
        )
    except insights_service.UnknownScopeError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except insights_service.AiInsightsServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await session.commit()
    return _insights_to_response(row)


@router.get("/ai-insights/latest", response_model=AiInsightSummaryResponse | None)
async def latest_ai_insight(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    scope: Annotated[str, Query(...)],
) -> AiInsightSummaryResponse | None:
    if scope not in insights_service.KNOWN_SCOPES:
        raise HTTPException(status_code=400, detail=f"unknown scope {scope!r}")
    row = await insights_service.get_latest(session=session, scope=scope)
    if row is None:
        return None
    return _insights_to_response(row)
