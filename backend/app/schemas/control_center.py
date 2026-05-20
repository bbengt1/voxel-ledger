"""Pydantic schemas for the control center (Phase 11.4, #196)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class SectionRead(BaseModel):
    count: int
    sample: list[dict[str, Any]]


class AmountSectionRead(SectionRead):
    amount_total: Decimal


class WsHealthRead(BaseModel):
    moonraker_ws_connected: bool
    last_event_at: datetime | None = None


class ControlCenterResponse(BaseModel):
    as_of: datetime
    pending_approvals: SectionRead
    low_stock_alerts: SectionRead
    overdue_invoices: AmountSectionRead
    overdue_bills: AmountSectionRead
    failed_jobs: SectionRead
    webhook_dlq: SectionRead
    ws_health: WsHealthRead


__all__ = [
    "AmountSectionRead",
    "ControlCenterResponse",
    "SectionRead",
    "WsHealthRead",
]
