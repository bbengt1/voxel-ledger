"""Pydantic schemas for the invoices API surface (Phase 7.3, #111).

Decimal fields round-trip as strings so JSON consumers don't lose
precision through a float hop. ``InvoiceItemCreate.kind`` is constrained
to the same literal as the DB enum.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customers import CustomerAddress

InvoiceStateLiteral = Literal["draft", "issued", "partially_paid", "paid", "overdue", "void"]
InvoiceItemKindLiteral = Literal["product", "job", "manual"]


# --- Items -----------------------------------------------------------------


class InvoiceItemCreate(BaseModel):
    """One line on a draft invoice. The service computes
    ``extended_amount`` from ``quantity * unit_price``."""

    kind: InvoiceItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    sku_or_job_number: str | None = Field(default=None, max_length=64)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    kind: InvoiceItemKindLiteral
    product_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    description: str
    sku_or_job_number: str | None = None
    quantity: Decimal
    unit_price: Decimal
    extended_amount: Decimal


# --- Invoice ---------------------------------------------------------------


class InvoiceCreate(BaseModel):
    customer_id: uuid.UUID
    due_at: datetime | None = None
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    notes: str | None = None
    items: list[InvoiceItemCreate] = Field(default_factory=list)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class InvoiceUpdate(BaseModel):
    """PATCH-style — only fields the caller wants to change.

    ``items`` replaces the entire line set when supplied. Only legal
    while the invoice is in ``draft``.
    """

    customer_id: uuid.UUID | None = None
    due_at: datetime | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    notes: str | None = None
    items: list[InvoiceItemCreate] | None = None


class InvoiceFromQuoteRequest(BaseModel):
    """Reserved payload for ``POST /api/v1/invoices/from-quote/{quote_id}``.

    Currently empty but defined so future per-conversion options (override
    due_at, override discount, etc.) have a stable place to land.
    """

    note: str | None = None


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    customer_id: uuid.UUID
    quote_id: uuid.UUID | None = None
    sale_id: uuid.UUID | None = None
    state: InvoiceStateLiteral
    issued_at: datetime | None = None
    due_at: datetime | None = None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    amount_outstanding: Decimal
    currency: str
    notes: str | None = None
    billing_address_snapshot: CustomerAddress | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[InvoiceItemResponse] = Field(default_factory=list)


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    next_cursor: str | None = None


class InvoiceStateTransitionRequest(BaseModel):
    """Reserved for any future per-transition payload (note, reason)."""

    note: str | None = None
