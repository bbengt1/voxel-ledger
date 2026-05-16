"""Pydantic schemas for late-fee policies + AR aging report (Phase 7.6, #114)."""

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
    amount: Decimal = Field(ge=0)
    grace_period_days: int = Field(default=0, ge=0)
    apply_after_days: int = Field(default=30, ge=0)
    compound_interval_days: int = Field(default=30, ge=1)
    is_active: bool = True
    notes: str | None = None


class LateFeePolicyUpdate(BaseModel):
    kind: LateFeeKindLiteral | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    grace_period_days: int | None = Field(default=None, ge=0)
    apply_after_days: int | None = Field(default=None, ge=0)
    compound_interval_days: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    notes: str | None = None


class LateFeePolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID | None = None
    kind: LateFeeKindLiteral
    amount: Decimal
    grace_period_days: int
    apply_after_days: int
    compound_interval_days: int
    is_active: bool
    notes: str | None = None
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class LateFeePolicyListResponse(BaseModel):
    items: list[LateFeePolicyResponse]


class LateFeeApplyNowResult(BaseModel):
    invoice_id: uuid.UUID
    policy_id: uuid.UUID
    debit_note_id: uuid.UUID
    amount: Decimal


class LateFeeApplyNowResponse(BaseModel):
    applied: list[LateFeeApplyNowResult]


# --- AR aging report -------------------------------------------------------


class AgingBucketResponse(BaseModel):
    label: str
    amount: Decimal


class AgingRowResponse(BaseModel):
    customer_id: uuid.UUID
    customer_number: str
    display_name: str
    total_outstanding: Decimal
    buckets: list[AgingBucketResponse]


class ArAgingReportResponse(BaseModel):
    as_of: datetime
    bucket_labels: list[str]
    rows: list[AgingRowResponse]
    grand_total: Decimal
    grand_total_by_bucket: list[Decimal]
