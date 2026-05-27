"""Pydantic schemas for the POS API surface (Phase 6.4, #96)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.sales import SaleResponse

PosCartStateLiteral = Literal["open", "checked_out", "voided"]
DiscountKindLiteral = Literal["percent", "amount"]


class PosCartItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    product_id: uuid.UUID | None = None
    description: str
    sku: str | None = None
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal = Decimal("0")
    discount_kind: DiscountKindLiteral | None = None
    extended_amount: Decimal


class PosCartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cashier_user_id: uuid.UUID
    channel_id: uuid.UUID
    state: PosCartStateLiteral
    # Phase 7.1 (#109): optional FK to a real customer aggregate. The
    # snapshot fields below stay populated for receipt display even when
    # ``customer_id`` is set.
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    discount_amount: Decimal = Decimal("0")
    discount_kind: DiscountKindLiteral | None = None
    sale_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    items: list[PosCartItemResponse] = Field(default_factory=list)

    subtotal: Decimal
    line_discount_total: Decimal
    cart_discount_amount: Decimal
    total: Decimal
    # Tax preview, derived from the cart's channel tax profile. Zero
    # when the channel has no tax profile attached.
    tax_amount: Decimal = Decimal("0")
    tax_profile_id: uuid.UUID | None = None
    tax_profile_name: str | None = None


class OpenCartRequest(BaseModel):
    channel_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)


class ScanRequest(BaseModel):
    barcode: str = Field(min_length=1, max_length=64)


class CartTaxProfileRequest(BaseModel):
    """Set or clear the per-cart tax-profile override. ``None`` reverts
    the cart to the channel's default."""

    tax_profile_id: uuid.UUID | None = None


class AddProductRequest(BaseModel):
    """Add a product to the cart by id (used by the typed-search picker
    on the POS screen). Quantity defaults to 1 so the picker matches the
    barcode-scan UX where each click adds one unit and re-stacks an
    existing line."""

    product_id: uuid.UUID
    quantity: Decimal = Field(default=Decimal("1"), gt=0)


class LineUpdateRequest(BaseModel):
    quantity: Decimal | None = None
    discount_kind: DiscountKindLiteral | None = None
    discount_value: Decimal | None = None


class DiscountRequest(BaseModel):
    kind: DiscountKindLiteral
    value: Decimal
    # Optional target — when ``line_number`` is provided, applies to that
    # line; otherwise applies as a cart-level discount.
    line_number: int | None = None


class CheckoutRequest(BaseModel):
    payment_method: str = Field(min_length=1, max_length=32)
    tendered_amount: Decimal
    customer_id: uuid.UUID | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    customer_email: str | None = Field(default=None, max_length=255)
    tax_amount: Decimal = Decimal("0")


class CheckoutResponse(BaseModel):
    sale: SaleResponse
    change_due: Decimal
    cart: PosCartResponse
