"""Pydantic schemas for the late-fee-policies API (Phase 7.6, #114)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LateFeeKindLiteral = Literal["percent_of_outstanding", "flat", "compound_percent"]


class LateFeePolicyCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    kind: LateFeeKindLiteral
    amount: Decimal = Field(gt=0)
    grace_period_days: int = Field(default=0, ge=0)
    apply_after_days: int = Field(default=30, ge=0)
    compound_interval_days: int = Field(default=30, gt=0)
    is_active: bool = True


class LateFeePolicyUpdate(BaseModel):
    customer_id: uuid.UUID | None = None
    kind: LateFeeKindLiteral | None = None
    amount: Decimal | None = None
    grace_period_days: int | None = None
    apply_after_days: int | None = None
    compound_interval_days: int | None = None
    is_active: bool | None = None


class LateFeePolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID | None
    kind: LateFeeKindLiteral
    amount: Decimal
    grace_period_days: int
    apply_after_days: int
    compound_interval_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LateFeePolicyListResponse(BaseModel):
    items: list[LateFeePolicyResponse]


class LateFeeApplyResponse(BaseModel):
    applied: int
    skipped: int
    deferred: bool
    fees_total: Decimal


class AgingBucketAmountSchema(BaseModel):
    label: str
    lower: int
    upper: int | None
    amount: Decimal


class CustomerAgingRowSchema(BaseModel):
    customer_id: uuid.UUID
    customer_number: str
    display_name: str
    total_outstanding: Decimal
    buckets: list[AgingBucketAmountSchema]


class ArAgingReportResponse(BaseModel):
    as_of: datetime
    bucket_days: list[int]
    rows: list[CustomerAgingRowSchema]
    grand_total: Decimal
    grand_total_buckets: list[AgingBucketAmountSchema]
