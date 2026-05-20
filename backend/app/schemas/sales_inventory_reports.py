"""Pydantic schemas for sales-by-period + inventory-valuation API (Phase 10.5, #180)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class SalesByPeriodRowResponse(BaseModel):
    channel_id: uuid.UUID
    bucket_start: date
    gross_sales: Decimal
    refunds: Decimal
    net_sales: Decimal
    order_count: int


class SalesByPeriodResponse(BaseModel):
    date_from: date
    date_to: date
    bucket: str
    channel_id: uuid.UUID | None = None
    rows: list[SalesByPeriodRowResponse]
    total_gross: Decimal
    total_refunds: Decimal
    total_net: Decimal
    total_orders: int


class InventoryValuationRowResponse(BaseModel):
    entity_kind: str
    entity_id: uuid.UUID
    name: str
    sku: str | None = None
    location_id: uuid.UUID
    location_name: str
    on_hand: Decimal
    unit_cost: Decimal
    valuation: Decimal


class InventoryValuationResponse(BaseModel):
    as_of: date
    location_id: uuid.UUID | None = None
    rows: list[InventoryValuationRowResponse]
    total_valuation: Decimal
    totals_by_kind: dict[str, Decimal]
    totals_by_location: dict[str, Decimal]
