"""Pydantic schemas for the vendors API surface (Phase 8.1, #128).

``billing_address`` and ``shipping_address`` round-trip through
``VendorAddress`` so callers get a typed shape and the OpenAPI codegen
sees fields rather than an opaque dict.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VendorStateLiteral = Literal["active", "archived"]


class VendorAddress(BaseModel):
    """Snapshot-friendly address shape for billing + shipping."""

    line1: str | None = Field(default=None, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=64)


# --- Contacts --------------------------------------------------------------


class VendorContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    role_label: str | None = Field(default=None, max_length=255)
    is_primary: bool = False


class VendorContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    role_label: str | None = Field(default=None, max_length=255)
    is_primary: bool | None = None


class VendorContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    role_label: str | None = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime


# --- Vendor ----------------------------------------------------------------


class VendorCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    primary_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: VendorAddress | None = None
    shipping_address: VendorAddress | None = None
    payment_terms_days: int = Field(default=30, ge=0, le=3650)
    default_expense_account_id: uuid.UUID | None = None
    default_ap_account_id: uuid.UUID | None = None
    tax_id: str | None = Field(default=None, max_length=64)
    is_1099_vendor: bool = False
    notes: str | None = None


class VendorUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    primary_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: VendorAddress | None = None
    shipping_address: VendorAddress | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=3650)
    default_expense_account_id: uuid.UUID | None = None
    default_ap_account_id: uuid.UUID | None = None
    tax_id: str | None = Field(default=None, max_length=64)
    is_1099_vendor: bool | None = None
    notes: str | None = None


class VendorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_number: str
    display_name: str
    legal_name: str | None = None
    primary_email: str | None = None
    phone: str | None = None
    billing_address: VendorAddress | None = None
    shipping_address: VendorAddress | None = None
    payment_terms_days: int
    default_expense_account_id: uuid.UUID | None = None
    default_ap_account_id: uuid.UUID | None = None
    tax_id: str | None = None
    is_1099_vendor: bool
    notes: str | None = None
    state: VendorStateLiteral
    created_at: datetime
    updated_at: datetime
    contacts: list[VendorContactResponse] = Field(default_factory=list)


class VendorListResponse(BaseModel):
    items: list[VendorResponse]
