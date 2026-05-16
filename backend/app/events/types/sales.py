"""Sales-bounded-context event types (Phase 6.1, #93).

The first sales aggregate is the ``sales_channel`` — a per-channel
configuration object (POS, marketplace, direct web, wholesale, other)
that owns its fee model and a couple of default GL account references.
Phase 6.2 adds the ``sale_order`` aggregate that consumes this config.

No secret-shaped fields exist on this aggregate today; the fee
percentages, flat fees, and account references are all configuration
metadata that the audit projection happily denormalizes.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_SALES_CHANNEL: str = "sales_channel"
AGGREGATE_TYPE_SALE: str = "sale"
AGGREGATE_TYPE_POS_CART: str = "pos_cart"
AGGREGATE_TYPE_SHIPMENT: str = "shipment"


class _SalesPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Sales channels ---------------------------------------------------------


class SalesChannelCreatedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID
    name: str
    slug: str
    kind: str
    fee_model: str
    fee_percent: str | None = None
    fee_flat: str | None = None
    default_revenue_account_id: uuid.UUID | None = None
    default_fee_account_id: uuid.UUID | None = None
    external_id_format_hint: str | None = None


class SalesChannelUpdatedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class SalesChannelArchivedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID


class SalesChannelUnarchivedPayload(_SalesPayloadBase):
    sales_channel_id: uuid.UUID


TYPE_SALES_CHANNEL_CREATED = "sales.SalesChannelCreated"
TYPE_SALES_CHANNEL_UPDATED = "sales.SalesChannelUpdated"
TYPE_SALES_CHANNEL_ARCHIVED = "sales.SalesChannelArchived"
TYPE_SALES_CHANNEL_UNARCHIVED = "sales.SalesChannelUnarchived"


register_event(TYPE_SALES_CHANNEL_CREATED, SalesChannelCreatedPayload)
register_event(TYPE_SALES_CHANNEL_UPDATED, SalesChannelUpdatedPayload)
register_event(TYPE_SALES_CHANNEL_ARCHIVED, SalesChannelArchivedPayload)
register_event(TYPE_SALES_CHANNEL_UNARCHIVED, SalesChannelUnarchivedPayload)


# --- Sales (Phase 6.2) ------------------------------------------------------
#
# CRITICAL: ``customer_email`` and ``notes`` MUST NEVER be whitelisted into
# the audit excerpt. The payload carries them (so replay can reconstruct
# the sale) but the audit denormalization keeps strictly to
# channel_id / sale_number / total_amount. See excerpts.py.


class SaleCreatedPayload(_SalesPayloadBase):
    sale_id: uuid.UUID
    sale_number: str
    channel_id: uuid.UUID
    external_order_id: str | None = None
    customer_name: str
    customer_email: str | None = None
    occurred_at: str
    subtotal: str
    discount_amount: str
    shipping_amount: str
    tax_amount: str
    channel_fee_amount: str
    total_amount: str
    state: str
    notes: str | None = None
    items: list[dict[str, Any]]


class SaleUpdatedPayload(_SalesPayloadBase):
    sale_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class SaleConfirmedPayload(_SalesPayloadBase):
    sale_id: uuid.UUID
    sale_number: str
    channel_id: uuid.UUID
    total_amount: str


class SaleFulfilledPayload(_SalesPayloadBase):
    sale_id: uuid.UUID
    sale_number: str


class SaleCancelledPayload(_SalesPayloadBase):
    sale_id: uuid.UUID
    sale_number: str


TYPE_SALE_CREATED = "sales.SaleCreated"
TYPE_SALE_UPDATED = "sales.SaleUpdated"
TYPE_SALE_CONFIRMED = "sales.SaleConfirmed"
TYPE_SALE_FULFILLED = "sales.SaleFulfilled"
TYPE_SALE_CANCELLED = "sales.SaleCancelled"


register_event(TYPE_SALE_CREATED, SaleCreatedPayload)
register_event(TYPE_SALE_UPDATED, SaleUpdatedPayload)
register_event(TYPE_SALE_CONFIRMED, SaleConfirmedPayload)
register_event(TYPE_SALE_FULFILLED, SaleFulfilledPayload)
register_event(TYPE_SALE_CANCELLED, SaleCancelledPayload)


# --- Sales posting trail (Phase 6.3) ----------------------------------------
#
# Emitted right AFTER SaleConfirmed / SaleCancelled by SalesService.confirm /
# cancel once the COGS service has fully posted (or reversed) the inventory
# and journal-entry side effects. The payloads carry the new audit traceable
# IDs (journal entry, inventory transactions) so the audit log can link a
# sale to its accounting + inventory footprint without re-querying.
#
# No PII surfaces here: sale_number + total_amount + ids only.


class SalePostedPayload(_SalesPayloadBase):
    sale_id: uuid.UUID
    sale_number: str
    journal_entry_id: uuid.UUID
    inventory_transaction_ids: list[uuid.UUID]
    total_amount: str


class SaleReversedPayload(_SalesPayloadBase):
    sale_id: uuid.UUID
    sale_number: str
    reversing_journal_entry_id: uuid.UUID
    original_journal_entry_id: uuid.UUID
    inventory_transaction_ids: list[uuid.UUID]


TYPE_SALE_POSTED = "sales.SalePosted"
TYPE_SALE_REVERSED = "sales.SaleReversed"


register_event(TYPE_SALE_POSTED, SalePostedPayload)
register_event(TYPE_SALE_REVERSED, SaleReversedPayload)


# --- Refunds (Phase 6.5) ----------------------------------------------------
#
# Refund payloads carry ``reason_code`` and ``refund_number`` plus ID
# references — never ``notes`` (operator free-text) and never any
# customer-email field (which doesn't appear here at all since refunds
# always reference a sale_id).

AGGREGATE_TYPE_REFUND: str = "refund"


class RefundCreatedPayload(_SalesPayloadBase):
    refund_id: uuid.UUID
    refund_number: str
    sale_id: uuid.UUID
    kind: str
    state: str
    total_amount: str
    restock_inventory: bool
    reason_code: str
    notes: str | None = None
    approval_request_id: uuid.UUID | None = None
    items: list[dict[str, Any]]


class RefundApprovedPayload(_SalesPayloadBase):
    refund_id: uuid.UUID
    refund_number: str
    sale_id: uuid.UUID
    total_amount: str
    reason_code: str
    approved_by_user_id: uuid.UUID


class RefundRejectedPayload(_SalesPayloadBase):
    refund_id: uuid.UUID
    refund_number: str
    sale_id: uuid.UUID
    rejected_by_user_id: uuid.UUID


class RefundPostedPayload(_SalesPayloadBase):
    refund_id: uuid.UUID
    refund_number: str
    sale_id: uuid.UUID
    total_amount: str
    reason_code: str
    reversing_journal_entry_id: uuid.UUID | None = None
    inventory_transaction_ids: list[uuid.UUID]


class RefundCancelledPayload(_SalesPayloadBase):
    refund_id: uuid.UUID
    refund_number: str
    sale_id: uuid.UUID


TYPE_REFUND_CREATED = "sales.RefundCreated"
TYPE_REFUND_APPROVED = "sales.RefundApproved"
TYPE_REFUND_REJECTED = "sales.RefundRejected"
TYPE_REFUND_POSTED = "sales.RefundPosted"
TYPE_REFUND_CANCELLED = "sales.RefundCancelled"


register_event(TYPE_REFUND_CREATED, RefundCreatedPayload)
register_event(TYPE_REFUND_APPROVED, RefundApprovedPayload)
register_event(TYPE_REFUND_REJECTED, RefundRejectedPayload)
register_event(TYPE_REFUND_POSTED, RefundPostedPayload)
register_event(TYPE_REFUND_CANCELLED, RefundCancelledPayload)


# --- POS carts (Phase 6.4) --------------------------------------------------
#
# CRITICAL: ``customer_email`` MUST NEVER be whitelisted into the audit
# excerpt. The payload may carry it (so the cart can be reconstructed) but
# the audit excerpts.py whitelist intentionally surfaces only cart_id,
# channel_id, line_number, total — no PII.


class PosCartOpenedPayload(_SalesPayloadBase):
    cart_id: uuid.UUID
    channel_id: uuid.UUID
    cashier_user_id: uuid.UUID


class PosLineAddedPayload(_SalesPayloadBase):
    cart_id: uuid.UUID
    line_number: int
    product_id: uuid.UUID | None = None
    sku: str | None = None
    quantity: str
    unit_price: str


class PosLineUpdatedPayload(_SalesPayloadBase):
    cart_id: uuid.UUID
    line_number: int
    before: dict[str, Any]
    after: dict[str, Any]


class PosLineRemovedPayload(_SalesPayloadBase):
    cart_id: uuid.UUID
    line_number: int


class PosCartCheckedOutPayload(_SalesPayloadBase):
    cart_id: uuid.UUID
    channel_id: uuid.UUID
    sale_id: uuid.UUID
    sale_number: str
    total: str


class PosCartVoidedPayload(_SalesPayloadBase):
    cart_id: uuid.UUID


TYPE_POS_CART_OPENED = "sales.PosCartOpened"
TYPE_POS_LINE_ADDED = "sales.PosLineAdded"
TYPE_POS_LINE_UPDATED = "sales.PosLineUpdated"
TYPE_POS_LINE_REMOVED = "sales.PosLineRemoved"
TYPE_POS_CART_CHECKED_OUT = "sales.PosCartCheckedOut"
TYPE_POS_CART_VOIDED = "sales.PosCartVoided"


register_event(TYPE_POS_CART_OPENED, PosCartOpenedPayload)
register_event(TYPE_POS_LINE_ADDED, PosLineAddedPayload)
register_event(TYPE_POS_LINE_UPDATED, PosLineUpdatedPayload)
register_event(TYPE_POS_LINE_REMOVED, PosLineRemovedPayload)
register_event(TYPE_POS_CART_CHECKED_OUT, PosCartCheckedOutPayload)
register_event(TYPE_POS_CART_VOIDED, PosCartVoidedPayload)
# --- Shipments (Phase 6.6, #98) -------------------------------------------
#
# CRITICAL: the ``ship_to`` / ``ship_from`` JSON snapshots, the
# ``label_pdf_storage_key`` and any customer free-text MUST NEVER appear
# in the audit excerpt. The payloads carry them so the event log can
# reconstruct the shipment, but the projection whitelist (see
# ``projections/audit/excerpts.py``) keeps strictly to carrier,
# service_level, tracking_number, cost_amount, and IDs.


class ShippingLabelPurchasedPayload(_SalesPayloadBase):
    shipment_id: uuid.UUID
    sale_id: uuid.UUID
    carrier: str
    service_level: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None
    cost_amount: str
    label_pdf_storage_key: str | None = None


class ShipmentShippedPayload(_SalesPayloadBase):
    shipment_id: uuid.UUID
    sale_id: uuid.UUID
    carrier: str
    tracking_number: str | None = None


class ShipmentDeliveredPayload(_SalesPayloadBase):
    shipment_id: uuid.UUID
    sale_id: uuid.UUID
    carrier: str
    tracking_number: str | None = None


class ShipmentCancelledPayload(_SalesPayloadBase):
    shipment_id: uuid.UUID
    sale_id: uuid.UUID
    carrier: str
    void_requested: bool = False


TYPE_SHIPPING_LABEL_PURCHASED = "sales.ShippingLabelPurchased"
TYPE_SHIPMENT_SHIPPED = "sales.ShipmentShipped"
TYPE_SHIPMENT_DELIVERED = "sales.ShipmentDelivered"
TYPE_SHIPMENT_CANCELLED = "sales.ShipmentCancelled"


register_event(TYPE_SHIPPING_LABEL_PURCHASED, ShippingLabelPurchasedPayload)
register_event(TYPE_SHIPMENT_SHIPPED, ShipmentShippedPayload)
register_event(TYPE_SHIPMENT_DELIVERED, ShipmentDeliveredPayload)
register_event(TYPE_SHIPMENT_CANCELLED, ShipmentCancelledPayload)
