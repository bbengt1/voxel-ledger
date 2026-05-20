"""Pydantic schemas for the cash-flow API (Phase 10.3, #178)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class CashFlowLineResponse(BaseModel):
    section: str
    line_item: str
    amount: Decimal


class CashFlowResponse(BaseModel):
    date_from: date
    date_to: date
    division_id: uuid.UUID | None = None
    operating_lines: list[CashFlowLineResponse]
    operating_total: Decimal
    investing_lines: list[CashFlowLineResponse]
    investing_total: Decimal
    financing_lines: list[CashFlowLineResponse]
    financing_total: Decimal
    net_change_in_cash: Decimal
    reconciliation_residual: Decimal
