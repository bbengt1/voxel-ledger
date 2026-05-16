"""Pydantic schemas for the bills API surface (Phase 8.2, #129).

Mirror of ``app.schemas.invoices`` for the AP-side bill aggregate.
Decimal fields round-trip as strings so JSON consumers don't lose
precision through a float hop. ``BillItemCreate.kind`` is constrained
to the same literal as the DB enum.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vendors import VendorAddress

BillStateLiteral = Literal["draft", "issued", "partially_paid", "paid", "overdue", "void"]
BillItemKindLiteral = Literal["expense_category", "manual"]


# --- Items -----------------------------------------------------------------


class BillItemCreate(BaseModel):
    """One line on a draft bill. The service computes ``extended_amount``
    from ``quantity * unit_price``."""

    kind: BillItemKindLiteral
    expense_category_id: uuid.UUID | None = None
    description: str = Field(min_length=1)
    vendor_sku: str | None = Field(default=None, max_length=64)
    quantity: Decimal = Field(default=Decimal("1"))
    unit_price: Decimal
    expense_account_id_override: uuid.UUID | None = None


class BillItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    kind: BillItemKindLiteral
    expense_category_id: uuid.UUID | None = None
    description: str
    vendor_sku: str | None = None
    quantity: Decimal
    unit_price: Decimal
    extended_amount: Decimal
    expense_account_id_override: uuid.UUID | None = None


# --- Bill ------------------------------------------------------------------


class BillCreate(BaseModel):
    vendor_id: uuid.UUID
    due_at: datetime | None = None
    vendor_invoice_number: str | None = Field(default=None, max_length=64)
    discount_amount: Decimal = Field(default=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"))
    notes: str | None = None
    items: list[BillItemCreate] = Field(default_factory=list)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class BillUpdate(BaseModel):
    """PATCH-style — only fields the caller wants to change.

    ``items`` replaces the entire line set when supplied. Only legal
    while the bill is in ``draft``.
    """

    vendor_id: uuid.UUID | None = None
    due_at: datetime | None = None
    vendor_invoice_number: str | None = None
    discount_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    notes: str | None = None
    items: list[BillItemCreate] | None = None


class BillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_number: str
    vendor_id: uuid.UUID
    state: BillStateLiteral
    issued_at: datetime | None = None
    due_at: datetime | None = None
    vendor_invoice_number: str | None = None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    amount_outstanding: Decimal
    currency: str
    notes: str | None = None
    billing_address_snapshot: VendorAddress | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[BillItemResponse] = Field(default_factory=list)


class BillListResponse(BaseModel):
    items: list[BillResponse]
    next_cursor: str | None = None


class BillStateTransitionRequest(BaseModel):
    """Reserved for any future per-transition payload (note, reason)."""

    note: str | None = None
