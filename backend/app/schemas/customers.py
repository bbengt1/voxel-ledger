"""Pydantic schemas for the customers API surface (Phase 7.1, #109).

``billing_address`` and ``shipping_address`` round-trip through
``CustomerAddress`` so callers get a typed shape and the OpenAPI codegen
sees fields rather than an opaque dict.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CustomerStateLiteral = Literal["active", "archived"]


class CustomerAddress(BaseModel):
    """Snapshot-friendly address shape for billing + shipping.

    All fields are optional so callers can stage a partially complete
    address; the service stores the object as-is.
    """

    line1: str | None = Field(default=None, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=128)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=64)


# --- Contacts --------------------------------------------------------------


class CustomerContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    role_label: str | None = Field(default=None, max_length=255)
    is_primary: bool = False


class CustomerContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    role_label: str | None = Field(default=None, max_length=255)
    is_primary: bool | None = None


class CustomerContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    name: str
    email: str | None = None
    phone: str | None = None
    role_label: str | None = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime


# --- Customer --------------------------------------------------------------


class CustomerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    primary_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: CustomerAddress | None = None
    shipping_address: CustomerAddress | None = None
    payment_terms_days: int = Field(default=30, ge=0, le=3650)
    default_revenue_account_id: uuid.UUID | None = None
    default_ar_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    notes: str | None = None


class CustomerUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    primary_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    billing_address: CustomerAddress | None = None
    shipping_address: CustomerAddress | None = None
    payment_terms_days: int | None = Field(default=None, ge=0, le=3650)
    default_revenue_account_id: uuid.UUID | None = None
    default_ar_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    notes: str | None = None


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_number: str
    display_name: str
    legal_name: str | None = None
    primary_email: str | None = None
    phone: str | None = None
    billing_address: CustomerAddress | None = None
    shipping_address: CustomerAddress | None = None
    payment_terms_days: int
    default_revenue_account_id: uuid.UUID | None = None
    default_ar_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    notes: str | None = None
    state: CustomerStateLiteral
    created_at: datetime
    updated_at: datetime
    contacts: list[CustomerContactResponse] = Field(default_factory=list)


class CustomerListResponse(BaseModel):
    items: list[CustomerResponse]
