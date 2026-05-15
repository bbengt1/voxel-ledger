"""Pydantic schemas for the sales API surface (Phase 6.2, #94).

Decimal fields round-trip as strings so JSON consumers don't lose
precision through a float hop. ``SaleItemCreate.kind`` is constrained to
the same literal as the DB enum.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SaleStateLiteral = Literal["draft", "confirmed", "fulfilled", "cancelled"]
SaleItemKindLiteral = Literal["product", "job", "manual"]


# --- Items -----------------------------------------------------------------


class SaleItemCreate(BaseModel):
    """One line on a draft sale. The service computes ``extended_amount``
    from ``quantity * unit_price`` — the caller doesn't supply it.

    ``description`` and ``sku_or_job_number`` are snapshotted onto the
    sale_item row at create/update time so later catalog edits don't
    rewrite history.
    """

    kind: SaleItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    sku_or_job_number: str | None = Field(default=None, max_length=64)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal


class SaleItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    kind: SaleItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str
    sku_or_job_number: str | None = None
    quantity: Decimal
    unit_price: Decimal
    extended_amount: Decimal


# --- Sale ------------------------------------------------------------------


class SaleCreate(BaseModel):
    channel_id: uuid.UUID
    external_order_id: str | None = None
    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    occurred_at: datetime
    discount_amount: Decimal = Field(default=Decimal("0"))
    shipping_amount: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    notes: str | None = None
    items: list[SaleItemCreate] = Field(default_factory=list)


class SaleUpdate(BaseModel):
    """PATCH-style — only fields the caller wants to change.

    ``items`` replaces the entire line set when supplied (simplest model
    for a draft). Omit to keep existing lines.
    """

    channel_id: uuid.UUID | None = None
    external_order_id: str | None = None
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None
    discount_amount: Decimal | None = None
    shipping_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    notes: str | None = None
    items: list[SaleItemCreate] | None = None


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sale_number: str
    channel_id: uuid.UUID
    external_order_id: str | None = None
    customer_name: str
    customer_email: str | None = None
    occurred_at: datetime
    recorded_at: datetime
    subtotal: Decimal
    discount_amount: Decimal
    shipping_amount: Decimal
    tax_amount: Decimal
    channel_fee_amount: Decimal
    total_amount: Decimal
    state: SaleStateLiteral
    notes: str | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[SaleItemResponse] = Field(default_factory=list)


class SaleListResponse(BaseModel):
    items: list[SaleResponse]
    next_cursor: str | None = None


class SaleStateTransitionRequest(BaseModel):
    """Reserved for any future per-transition payload (note, reason).

    Phase 6.2 ships with zero-body state transitions — the endpoint paths
    encode the target state — but the schema is wired so Phase 6.3 can
    extend it without breaking codegen.
    """

    note: str | None = None
