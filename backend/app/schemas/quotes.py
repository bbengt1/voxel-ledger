"""Pydantic schemas for the quotes API surface (Phase 7.2, #110).

Decimal fields round-trip as strings so JSON consumers don't lose
precision through a float hop. ``QuoteItemCreate.kind`` is constrained to
the same literal as the DB enum.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customers import CustomerAddress

QuoteStateLiteral = Literal["draft", "sent", "accepted", "declined", "expired", "cancelled"]
QuoteItemKindLiteral = Literal["product", "job", "manual"]


# --- Items -----------------------------------------------------------------


class QuoteItemCreate(BaseModel):
    """One line on a draft quote. The service computes
    ``extended_amount`` from ``quantity * unit_price``."""

    kind: QuoteItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    sku_or_job_number: str | None = Field(default=None, max_length=64)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal


class QuoteItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    kind: QuoteItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str
    sku_or_job_number: str | None = None
    quantity: Decimal
    unit_price: Decimal
    extended_amount: Decimal


# --- Quote -----------------------------------------------------------------


class QuoteCreate(BaseModel):
    customer_id: uuid.UUID
    valid_until: datetime | None = None
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    notes: str | None = None
    items: list[QuoteItemCreate] = Field(default_factory=list)


class QuoteUpdate(BaseModel):
    """PATCH-style — only fields the caller wants to change.

    ``items`` replaces the entire line set when supplied. Only legal
    while the quote is in ``draft``.
    """

    customer_id: uuid.UUID | None = None
    valid_until: datetime | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    notes: str | None = None
    items: list[QuoteItemCreate] | None = None


class QuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID
    state: QuoteStateLiteral
    issued_at: datetime | None = None
    valid_until: datetime | None = None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    notes: str | None = None
    billing_address_snapshot: CustomerAddress | None = None
    accepted_invoice_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[QuoteItemResponse] = Field(default_factory=list)


class QuoteListResponse(BaseModel):
    items: list[QuoteResponse]
    next_cursor: str | None = None


class QuoteStateTransitionRequest(BaseModel):
    """Reserved for any future per-transition payload (note, reason)."""

    note: str | None = None


class QuoteConvertToInvoiceResponse(BaseModel):
    """Returned by ``POST /api/v1/quotes/{id}/convert-to-invoice`` once
    Phase 7.3 lands. Until then the endpoint returns 501."""

    invoice_id: uuid.UUID
