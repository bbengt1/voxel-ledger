"""Pydantic schemas for the dashboard API (Phase 10.6, #181)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class DashboardKpisResponse(BaseModel):
    as_of: date
    cash_on_hand: Decimal
    accounts_receivable: Decimal
    accounts_payable: Decimal
    overdue_invoice_count: int
    overdue_bill_count: int
    low_stock_alert_count: int
    net_income_mtd: Decimal
    net_income_ytd: Decimal
    last_updated_at: datetime
