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
