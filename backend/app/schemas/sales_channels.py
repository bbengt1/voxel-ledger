"""Pydantic schemas for the sales-channels API surface (Phase 6.1, #93).

``fee_percent`` and ``fee_flat`` round-trip as Decimal strings — the
service does all interior math in Decimal and serializing as strings
keeps JSON consumers from losing precision through a float hop.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SalesChannelKindLiteral = Literal[
    "pos",
    "marketplace",
    "direct_web",
    "wholesale",
    "other",
]
SalesChannelFeeModelLiteral = Literal[
    "none",
    "flat",
    "percent",
    "percent_plus_flat",
]


class SalesChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    kind: SalesChannelKindLiteral
    fee_model: SalesChannelFeeModelLiteral
    fee_percent: Decimal | None = None
    fee_flat: Decimal | None = None
    is_active: bool
    default_revenue_account_id: uuid.UUID | None = None
    default_fee_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    external_id_format_hint: str | None = None
    created_at: datetime
    updated_at: datetime


class SalesChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=64)
    kind: SalesChannelKindLiteral
    fee_model: SalesChannelFeeModelLiteral
    fee_percent: Decimal | None = None
    fee_flat: Decimal | None = None
    default_revenue_account_id: uuid.UUID | None = None
    default_fee_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    external_id_format_hint: str | None = Field(default=None, max_length=1024)


class SalesChannelUpdate(BaseModel):
    """PATCH-style — only fields the caller wants to change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=64)
    kind: SalesChannelKindLiteral | None = None
    fee_model: SalesChannelFeeModelLiteral | None = None
    fee_percent: Decimal | None = None
    fee_flat: Decimal | None = None
    default_revenue_account_id: uuid.UUID | None = None
    default_fee_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    external_id_format_hint: str | None = Field(default=None, max_length=1024)


class SalesChannelListResponse(BaseModel):
    items: list[SalesChannelResponse]
