"""Pydantic schemas for the materials API surface (Phase 2.1, 3.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

# 2-decimal display quantum for grams and dollar amounts. Storage stays
# Numeric(18, 6); this only affects the JSON response surface.
_DISPLAY_QUANTUM = Decimal("0.01")


def _round2(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_DISPLAY_QUANTUM, rounding=ROUND_HALF_UP)


class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand: str | None = None
    material_type: str
    color: str | None = None
    density_g_per_cm3: Decimal | None = None
    spool_weight_grams: Decimal
    current_cost_per_gram: Decimal
    # Phase 3.3 (#52): on-hand grams now live in ``inventory_on_hand``;
    # the API exposes the cross-location total plus a per-location map.
    total_on_hand: Decimal = Field(default=Decimal("0"))
    per_location_on_hand: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    low_stock_threshold_grams: Decimal | None = None
    is_archived: bool
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    # Display rounding to 2 decimals. Storage is Numeric(18, 6); the
    # round only applies to the JSON response surface (#11).
    @field_serializer("spool_weight_grams", "current_cost_per_gram", "total_on_hand")
    def _ser_round2_required(self, value: Decimal) -> Decimal:
        return _round2(value) or Decimal("0.00")

    @field_serializer("low_stock_threshold_grams")
    def _ser_round2_optional(self, value: Decimal | None) -> Decimal | None:
        return _round2(value)

    @field_serializer("per_location_on_hand", when_used="json")
    def _ser_per_location(self, value: dict[uuid.UUID, Decimal]) -> dict[str, Decimal]:
        return {str(k): _round2(v) or Decimal("0.00") for k, v in (value or {}).items()}


class MaterialReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID
    received_at: datetime
    grams: Decimal
    total_cost: Decimal
    unit_cost_at_receipt: Decimal
    vendor: str | None = None
    reference: str | None = None
    notes: str | None = None

    @field_serializer("grams", "total_cost", "unit_cost_at_receipt")
    def _ser_round2(self, value: Decimal) -> Decimal:
        return _round2(value) or Decimal("0.00")


class MaterialDetailResponse(MaterialResponse):
    """Material + the most recent 10 receipts (newest first).

    ``weighted_avg_cost_per_gram`` mirrors ``current_cost_per_gram``
    (already a running weighted average maintained by the
    ``material_cost`` projection from the receipt stream). v1 caveat:
    this is the all-time receipts weighted average, not a true
    moving-average that re-baselines on consumption — fine for a small
    catalog where receipts dominate inventory turnover.
    ``on_hand_value = total_on_hand * weighted_avg_cost_per_gram``.
    """

    recent_receipts: list[MaterialReceiptResponse] = Field(default_factory=list)
    weighted_avg_cost_per_gram: Decimal = Field(default=Decimal("0"))
    on_hand_value: Decimal = Field(default=Decimal("0"))

    @field_serializer("weighted_avg_cost_per_gram", "on_hand_value")
    def _ser_detail_round2(self, value: Decimal) -> Decimal:
        return _round2(value) or Decimal("0.00")


class MaterialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    material_type: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=64)
    density_g_per_cm3: Decimal | None = Field(default=None, ge=0)
    spool_weight_grams: Decimal = Field(gt=0)
    low_stock_threshold_grams: Decimal | None = Field(default=None, ge=0)
    custom_fields: dict[str, Any] | None = None


class MaterialUpdateRequest(BaseModel):
    """PATCH-style — only fields the user wants to change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    brand: str | None = Field(default=None, max_length=255)
    material_type: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=64)
    density_g_per_cm3: Decimal | None = Field(default=None, ge=0)
    spool_weight_grams: Decimal | None = Field(default=None, gt=0)
    low_stock_threshold_grams: Decimal | None = Field(default=None, ge=0)
    custom_fields: dict[str, Any] | None = None


class MaterialListResponse(BaseModel):
    items: list[MaterialResponse]
    next_cursor: str | None = None


class MaterialReceiptCreateRequest(BaseModel):
    """Spool-centric receipt entry (#11).

    The operator records purchased material as a whole number of spools
    plus an optional partial-spool ``extra_grams`` measurement and a
    ``price_per_spool``. The service derives total grams and total cost
    from these fields and the parent material's ``spool_weight_grams``.

    Cross-field rules:
    - ``spools + extra_grams > 0`` (a zero-quantity receipt is a no-op).
    - ``extra_grams < spool_weight_grams`` (an "extra" can't exceed one
      full spool; that case should be recorded as another whole spool).
    """

    spools: int = Field(ge=0)
    extra_grams: Decimal = Field(default=Decimal("0"), ge=0)
    price_per_spool: Decimal = Field(ge=0)
    vendor: str | None = Field(default=None, max_length=255)
    reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @model_validator(mode="after")
    def _nonzero_quantity(self) -> MaterialReceiptCreateRequest:
        if self.spools == 0 and self.extra_grams <= 0:
            raise ValueError("receipt must include at least one spool or some extra_grams")
        return self


class MaterialReceiptListResponse(BaseModel):
    items: list[MaterialReceiptResponse]
    next_cursor: str | None = None
