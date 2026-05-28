"""Control Center API (Phase 11.4, #196)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.control_center import (
    AmountSectionRead,
    ControlCenterResponse,
    SectionRead,
    WsHealthRead,
)
from app.services import control_center as service

router = APIRouter(prefix="/control-center", tags=["control-center"])

_READ_ROLES = ("owner", "bookkeeper")


@router.get("", response_model=ControlCenterResponse)
async def get_control_center(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> ControlCenterResponse:
    cc = await service.build(session)
    return ControlCenterResponse(
        as_of=cc.as_of,
        pending_approvals=SectionRead(
            count=cc.pending_approvals.count, sample=cc.pending_approvals.sample
        ),
        low_stock_alerts=SectionRead(
            count=cc.low_stock_alerts.count, sample=cc.low_stock_alerts.sample
        ),
        overdue_invoices=AmountSectionRead(
            count=cc.overdue_invoices.count,
            amount_total=cc.overdue_invoices.amount_total,
            sample=cc.overdue_invoices.sample,
        ),
        overdue_bills=AmountSectionRead(
            count=cc.overdue_bills.count,
            amount_total=cc.overdue_bills.amount_total,
            sample=cc.overdue_bills.sample,
        ),
        failed_jobs=SectionRead(count=cc.failed_jobs.count, sample=cc.failed_jobs.sample),
        webhook_dlq=SectionRead(count=cc.webhook_dlq.count, sample=cc.webhook_dlq.sample),
        ws_health=WsHealthRead(
            moonraker_ws_connected=cc.ws_health.moonraker_ws_connected,
            last_event_at=cc.ws_health.last_event_at,
        ),
    )
