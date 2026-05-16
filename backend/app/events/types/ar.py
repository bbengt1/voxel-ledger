"""AR-bounded-context event types (Phase 7.1, #109).

Aggregates landing here:

* ``customer`` (Phase 7.1) — the AR-side subject identity. Created /
  updated / archived / unarchived events, plus the nested contact CRUD.

CRITICAL PII RULE
-----------------
``primary_email``, ``phone``, ``billing_address``, ``shipping_address``,
and ``notes`` MUST NEVER be whitelisted into the audit excerpt. The
payload carries them so the event log can reconstruct the customer, but
the audit denormalization keeps strictly to ``customer_number`` and
``display_name``. See ``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_CUSTOMER: str = "customer"
AGGREGATE_TYPE_QUOTE: str = "quote"
AGGREGATE_TYPE_INVOICE: str = "invoice"


class _ARPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Customers --------------------------------------------------------------


class CustomerCreatedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    customer_number: str
    display_name: str
    legal_name: str | None = None
    primary_email: str | None = None
    phone: str | None = None
    payment_terms_days: int
    default_revenue_account_id: uuid.UUID | None = None
    default_ar_account_id: uuid.UUID | None = None
    tax_profile_id: uuid.UUID | None = None
    state: str


class CustomerUpdatedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class CustomerArchivedPayload(_ARPayloadBase):
    customer_id: uuid.UUID


class CustomerUnarchivedPayload(_ARPayloadBase):
    customer_id: uuid.UUID


class CustomerContactAddedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    contact_id: uuid.UUID
    name: str
    role_label: str | None = None
    is_primary: bool


class CustomerContactUpdatedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    contact_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class CustomerContactRemovedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    contact_id: uuid.UUID


TYPE_CUSTOMER_CREATED = "ar.CustomerCreated"
TYPE_CUSTOMER_UPDATED = "ar.CustomerUpdated"
TYPE_CUSTOMER_ARCHIVED = "ar.CustomerArchived"
TYPE_CUSTOMER_UNARCHIVED = "ar.CustomerUnarchived"
TYPE_CUSTOMER_CONTACT_ADDED = "ar.CustomerContactAdded"
TYPE_CUSTOMER_CONTACT_UPDATED = "ar.CustomerContactUpdated"
TYPE_CUSTOMER_CONTACT_REMOVED = "ar.CustomerContactRemoved"


register_event(TYPE_CUSTOMER_CREATED, CustomerCreatedPayload)
register_event(TYPE_CUSTOMER_UPDATED, CustomerUpdatedPayload)
register_event(TYPE_CUSTOMER_ARCHIVED, CustomerArchivedPayload)
register_event(TYPE_CUSTOMER_UNARCHIVED, CustomerUnarchivedPayload)
register_event(TYPE_CUSTOMER_CONTACT_ADDED, CustomerContactAddedPayload)
register_event(TYPE_CUSTOMER_CONTACT_UPDATED, CustomerContactUpdatedPayload)
register_event(TYPE_CUSTOMER_CONTACT_REMOVED, CustomerContactRemovedPayload)


# --- Quotes (Phase 7.2, #110) ------------------------------------------------
#
# PII NOTE: ``notes`` and ``billing_address_snapshot`` are carried in
# create/update payloads so replay can reconstruct the quote, but the
# audit-excerpt whitelist NEVER surfaces them. See
# ``app/projections/audit/excerpts.py``.


class QuoteCreatedPayload(_ARPayloadBase):
    quote_id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID
    state: str
    issued_at: str | None = None
    valid_until: str | None = None
    subtotal: str
    discount_amount: str
    tax_amount: str
    total_amount: str
    notes: str | None = None
    billing_address_snapshot: dict[str, Any] | None = None
    items: list[dict[str, Any]] = []


class QuoteUpdatedPayload(_ARPayloadBase):
    quote_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class QuoteSentPayload(_ARPayloadBase):
    quote_id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID
    total_amount: str
    issued_at: str


class QuoteAcceptedPayload(_ARPayloadBase):
    quote_id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID
    total_amount: str


class QuoteDeclinedPayload(_ARPayloadBase):
    quote_id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID


class QuoteExpiredPayload(_ARPayloadBase):
    quote_id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID


class QuoteCancelledPayload(_ARPayloadBase):
    quote_id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID


class QuoteConvertedToInvoicePayload(_ARPayloadBase):
    quote_id: uuid.UUID
    quote_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    total_amount: str


TYPE_QUOTE_CREATED = "ar.QuoteCreated"
TYPE_QUOTE_UPDATED = "ar.QuoteUpdated"
TYPE_QUOTE_SENT = "ar.QuoteSent"
TYPE_QUOTE_ACCEPTED = "ar.QuoteAccepted"
TYPE_QUOTE_DECLINED = "ar.QuoteDeclined"
TYPE_QUOTE_EXPIRED = "ar.QuoteExpired"
TYPE_QUOTE_CANCELLED = "ar.QuoteCancelled"
TYPE_QUOTE_CONVERTED_TO_INVOICE = "ar.QuoteConvertedToInvoice"


register_event(TYPE_QUOTE_CREATED, QuoteCreatedPayload)
register_event(TYPE_QUOTE_UPDATED, QuoteUpdatedPayload)
register_event(TYPE_QUOTE_SENT, QuoteSentPayload)
register_event(TYPE_QUOTE_ACCEPTED, QuoteAcceptedPayload)
register_event(TYPE_QUOTE_DECLINED, QuoteDeclinedPayload)
register_event(TYPE_QUOTE_EXPIRED, QuoteExpiredPayload)
register_event(TYPE_QUOTE_CANCELLED, QuoteCancelledPayload)
register_event(TYPE_QUOTE_CONVERTED_TO_INVOICE, QuoteConvertedToInvoicePayload)


# --- Invoices (Phase 7.3, #111) ---------------------------------------------
#
# PII NOTE: ``notes`` and ``billing_address_snapshot`` are carried in
# create/update payloads so replay can reconstruct the invoice, but the
# audit-excerpt whitelist NEVER surfaces them. See
# ``app/projections/audit/excerpts.py``.


class InvoiceCreatedPayload(_ARPayloadBase):
    invoice_id: uuid.UUID
    invoice_number: str
    customer_id: uuid.UUID
    quote_id: uuid.UUID | None = None
    sale_id: uuid.UUID | None = None
    state: str
    issued_at: str | None = None
    due_at: str | None = None
    subtotal: str
    discount_amount: str
    tax_amount: str
    total_amount: str
    currency: str = "USD"
    notes: str | None = None
    billing_address_snapshot: dict[str, Any] | None = None
    items: list[dict[str, Any]] = []


class InvoiceUpdatedPayload(_ARPayloadBase):
    invoice_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class InvoiceIssuedPayload(_ARPayloadBase):
    invoice_id: uuid.UUID
    invoice_number: str
    customer_id: uuid.UUID
    total_amount: str
    issued_at: str
    due_at: str | None = None
    journal_entry_id: uuid.UUID


class InvoicePostedPayload(_ARPayloadBase):
    invoice_id: uuid.UUID
    invoice_number: str
    journal_entry_id: uuid.UUID
    total_amount: str


class InvoiceVoidedPayload(_ARPayloadBase):
    invoice_id: uuid.UUID
    invoice_number: str
    customer_id: uuid.UUID


class InvoiceReversedPayload(_ARPayloadBase):
    invoice_id: uuid.UUID
    invoice_number: str
    reversing_journal_entry_id: uuid.UUID
    original_journal_entry_id: uuid.UUID


TYPE_INVOICE_CREATED = "ar.InvoiceCreated"
TYPE_INVOICE_UPDATED = "ar.InvoiceUpdated"
TYPE_INVOICE_ISSUED = "ar.InvoiceIssued"
TYPE_INVOICE_POSTED = "ar.InvoicePosted"
TYPE_INVOICE_VOIDED = "ar.InvoiceVoided"
TYPE_INVOICE_REVERSED = "ar.InvoiceReversed"


register_event(TYPE_INVOICE_CREATED, InvoiceCreatedPayload)
register_event(TYPE_INVOICE_UPDATED, InvoiceUpdatedPayload)
register_event(TYPE_INVOICE_ISSUED, InvoiceIssuedPayload)
register_event(TYPE_INVOICE_POSTED, InvoicePostedPayload)
register_event(TYPE_INVOICE_VOIDED, InvoiceVoidedPayload)
register_event(TYPE_INVOICE_REVERSED, InvoiceReversedPayload)
