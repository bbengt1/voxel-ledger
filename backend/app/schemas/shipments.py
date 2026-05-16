"""Pydantic schemas for the shipments API (Phase 6.6, #98)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _ShipBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShipmentCreate(_ShipBase):
    ship_to: dict[str, Any]
    weight_grams: int | None = Field(default=None, ge=0)
    dimensions_cm: dict[str, Any] | None = None
    service_level: str | None = None
    carrier_hint: str | None = None


class ShipmentResponse(_ShipBase):
    id: uuid.UUID
    sale_id: uuid.UUID
    state: str
    carrier: str
    service_level: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None
    label_pdf_storage_key: str | None = None
    cost_amount: Decimal
    weight_grams: int | None = None
    dimensions_cm: dict[str, Any] | None = None
    ship_from: dict[str, Any]
    ship_to: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ShipmentTransitionRequest(_ShipBase):
    """Body for the shipment state-transition endpoints — empty today,
    declared so callers can attach future fields (notes, override flags)
    without breaking the contract."""


__all__ = [
    "ShipmentCreate",
    "ShipmentResponse",
    "ShipmentTransitionRequest",
]
