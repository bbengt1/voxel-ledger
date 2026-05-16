"""AP-bounded-context event types (Phase 8.1, #128).

Aggregates landing here:

* ``vendor`` (Phase 8.1) — the AP-side subject identity. Created /
  updated / archived / unarchived events, plus the nested contact CRUD.

CRITICAL PII RULE
-----------------
``primary_email``, ``phone``, ``billing_address``, ``shipping_address``,
``tax_id``, and ``notes`` MUST NEVER be whitelisted into the audit
excerpt. The payload carries them so the event log can reconstruct the
vendor, but the audit denormalization keeps strictly to
``vendor_number`` and ``display_name``. See
``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event

AGGREGATE_TYPE_VENDOR: str = "vendor"
AGGREGATE_TYPE_VENDOR_CONTACT: str = "vendor_contact"
AGGREGATE_TYPE_BILL: str = "bill"
AGGREGATE_TYPE_BILL_PAYMENT: str = "bill_payment"


class _APPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Vendors ---------------------------------------------------------------


class VendorCreatedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    vendor_number: str
    display_name: str
    legal_name: str | None = None
    primary_email: str | None = None
    phone: str | None = None
    payment_terms_days: int
    default_expense_account_id: uuid.UUID | None = None
    default_ap_account_id: uuid.UUID | None = None
    tax_id: str | None = None
    is_1099_vendor: bool = False
    state: str


class VendorUpdatedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class VendorArchivedPayload(_APPayloadBase):
    vendor_id: uuid.UUID


class VendorUnarchivedPayload(_APPayloadBase):
    vendor_id: uuid.UUID


class VendorContactAddedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    contact_id: uuid.UUID
    name: str
    role_label: str | None = None
    is_primary: bool


class VendorContactUpdatedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    contact_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class VendorContactRemovedPayload(_APPayloadBase):
    vendor_id: uuid.UUID
    contact_id: uuid.UUID


TYPE_VENDOR_CREATED = "ap.VendorCreated"
TYPE_VENDOR_UPDATED = "ap.VendorUpdated"
TYPE_VENDOR_ARCHIVED = "ap.VendorArchived"
TYPE_VENDOR_UNARCHIVED = "ap.VendorUnarchived"
TYPE_VENDOR_CONTACT_ADDED = "ap.VendorContactAdded"
TYPE_VENDOR_CONTACT_UPDATED = "ap.VendorContactUpdated"
TYPE_VENDOR_CONTACT_REMOVED = "ap.VendorContactRemoved"


register_event(TYPE_VENDOR_CREATED, VendorCreatedPayload)
register_event(TYPE_VENDOR_UPDATED, VendorUpdatedPayload)
register_event(TYPE_VENDOR_ARCHIVED, VendorArchivedPayload)
register_event(TYPE_VENDOR_UNARCHIVED, VendorUnarchivedPayload)
register_event(TYPE_VENDOR_CONTACT_ADDED, VendorContactAddedPayload)
register_event(TYPE_VENDOR_CONTACT_UPDATED, VendorContactUpdatedPayload)
register_event(TYPE_VENDOR_CONTACT_REMOVED, VendorContactRemovedPayload)


# --- Bills (Phase 8.2, #129) ------------------------------------------------
#
# PII NOTE: ``notes`` and ``billing_address_snapshot`` are carried in
# create/update payloads so replay can reconstruct the bill, but the
# audit-excerpt whitelist NEVER surfaces them. See
# ``app/projections/audit/excerpts.py``.


class BillCreatedPayload(_APPayloadBase):
    bill_id: uuid.UUID
    bill_number: str
    vendor_id: uuid.UUID
    state: str
    issued_at: str | None = None
    due_at: str | None = None
    vendor_invoice_number: str | None = None
    subtotal: str
    discount_amount: str
    tax_amount: str
    total_amount: str
    currency: str = "USD"
    notes: str | None = None
    billing_address_snapshot: dict[str, Any] | None = None
    items: list[dict[str, Any]] = []


class BillUpdatedPayload(_APPayloadBase):
    bill_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class BillIssuedPayload(_APPayloadBase):
    bill_id: uuid.UUID
    bill_number: str
    vendor_id: uuid.UUID
    total_amount: str
    issued_at: str
    due_at: str | None = None
    journal_entry_id: uuid.UUID


class BillPostedPayload(_APPayloadBase):
    bill_id: uuid.UUID
    bill_number: str
    journal_entry_id: uuid.UUID
    total_amount: str


class BillVoidedPayload(_APPayloadBase):
    bill_id: uuid.UUID
    bill_number: str
    vendor_id: uuid.UUID


class BillReversedPayload(_APPayloadBase):
    bill_id: uuid.UUID
    bill_number: str
    reversing_journal_entry_id: uuid.UUID
    original_journal_entry_id: uuid.UUID


TYPE_BILL_CREATED = "ap.BillCreated"
TYPE_BILL_UPDATED = "ap.BillUpdated"
TYPE_BILL_ISSUED = "ap.BillIssued"
TYPE_BILL_POSTED = "ap.BillPosted"
TYPE_BILL_VOIDED = "ap.BillVoided"
TYPE_BILL_REVERSED = "ap.BillReversed"


register_event(TYPE_BILL_CREATED, BillCreatedPayload)
register_event(TYPE_BILL_UPDATED, BillUpdatedPayload)
register_event(TYPE_BILL_ISSUED, BillIssuedPayload)
register_event(TYPE_BILL_POSTED, BillPostedPayload)
register_event(TYPE_BILL_VOIDED, BillVoidedPayload)
register_event(TYPE_BILL_REVERSED, BillReversedPayload)


# --- Bill payments (Phase 8.3, #130) ----------------------------------------
#
# PII / sensitive-field rule for the audit excerpt:
# * ``reference_number`` (check #, wire id) and ``notes`` MUST NEVER be
#   whitelisted. They're captured on the row so replay can reconstruct
#   the payment, but the audit denormalization keeps strictly to
#   ``payment_number``, ``vendor_id``, ``amount``, ``method``, and the
#   JE id. See ``app/projections/audit/excerpts.py``.


class BillPaymentRecordedPayload(_APPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    vendor_id: uuid.UUID
    method: str
    reference_number: str | None = None
    amount: str
    occurred_at: str
    state: str
    notes: str | None = None


class BillPaymentAppliedPayload(_APPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    vendor_id: uuid.UUID
    bill_id: uuid.UUID
    bill_number: str
    amount_applied: str


class BillPaymentPostedPayload(_APPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    vendor_id: uuid.UUID
    amount: str
    method: str
    journal_entry_id: uuid.UUID


class BillPaymentUnappliedPayload(_APPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    vendor_id: uuid.UUID
    reversing_journal_entry_id: uuid.UUID | None = None
    original_journal_entry_id: uuid.UUID | None = None


class BillPaymentBouncedPayload(_APPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    vendor_id: uuid.UUID


class BillPaymentCancelledPayload(_APPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    vendor_id: uuid.UUID


TYPE_BILL_PAYMENT_RECORDED = "ap.BillPaymentRecorded"
TYPE_BILL_PAYMENT_APPLIED = "ap.BillPaymentApplied"
TYPE_BILL_PAYMENT_POSTED = "ap.BillPaymentPosted"
TYPE_BILL_PAYMENT_UNAPPLIED = "ap.BillPaymentUnapplied"
TYPE_BILL_PAYMENT_BOUNCED = "ap.BillPaymentBounced"
TYPE_BILL_PAYMENT_CANCELLED = "ap.BillPaymentCancelled"


register_event(TYPE_BILL_PAYMENT_RECORDED, BillPaymentRecordedPayload)
register_event(TYPE_BILL_PAYMENT_APPLIED, BillPaymentAppliedPayload)
register_event(TYPE_BILL_PAYMENT_POSTED, BillPaymentPostedPayload)
register_event(TYPE_BILL_PAYMENT_UNAPPLIED, BillPaymentUnappliedPayload)
register_event(TYPE_BILL_PAYMENT_BOUNCED, BillPaymentBouncedPayload)
register_event(TYPE_BILL_PAYMENT_CANCELLED, BillPaymentCancelledPayload)


# --- Bill overdue (Phase 8.4, #131) -----------------------------------------
#
# Mirrors ``ar.InvoiceOverdue``. Emitted by the overdue-bill marker worker
# when a bill transitions from ``issued`` / ``partially_paid`` to
# ``overdue`` because ``due_at`` has passed.


class BillOverduePayload(_APPayloadBase):
    bill_id: uuid.UUID
    bill_number: str
    vendor_id: uuid.UUID
    due_at: str
    days_overdue: int
    amount_outstanding: str


TYPE_BILL_OVERDUE = "ap.BillOverdue"

register_event(TYPE_BILL_OVERDUE, BillOverduePayload)
