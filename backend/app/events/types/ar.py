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
AGGREGATE_TYPE_PAYMENT: str = "payment"
AGGREGATE_TYPE_CREDIT_NOTE: str = "credit_note"
AGGREGATE_TYPE_DEBIT_NOTE: str = "debit_note"
AGGREGATE_TYPE_CUSTOMER_CREDIT: str = "customer_credit"
AGGREGATE_TYPE_RECURRING_INVOICE_TEMPLATE: str = "recurring_invoice_template"


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


# --- Payments (Phase 7.4, #112) ---------------------------------------------
#
# PII / sensitive-field rule for the audit excerpt:
# * ``reference`` (check number, card last-4, marketplace TX id) and
#   ``notes`` MUST NEVER be whitelisted. They're captured on the row so
#   replay can reconstruct the payment, but the audit denormalization
#   keeps strictly to ``payment_number``, ``customer_id``, ``amount``,
#   ``method``, and the JE id. See
#   ``app/projections/audit/excerpts.py``.


class PaymentRecordedPayload(_ARPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID
    method: str
    reference: str | None = None
    amount: str
    received_at: str
    state: str
    notes: str | None = None


class PaymentAppliedPayload(_ARPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID
    applications: list[dict[str, Any]]
    total_applied: str
    excess_to_credit: str


class PaymentPostedPayload(_ARPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID
    amount: str
    method: str
    journal_entry_id: uuid.UUID


class PaymentUnappliedPayload(_ARPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID
    reversing_journal_entry_id: uuid.UUID | None = None
    original_journal_entry_id: uuid.UUID | None = None


class PaymentBouncedPayload(_ARPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID


class PaymentCancelledPayload(_ARPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID


TYPE_PAYMENT_RECORDED = "ar.PaymentRecorded"
TYPE_PAYMENT_APPLIED = "ar.PaymentApplied"
TYPE_PAYMENT_POSTED = "ar.PaymentPosted"
TYPE_PAYMENT_UNAPPLIED = "ar.PaymentUnapplied"
TYPE_PAYMENT_BOUNCED = "ar.PaymentBounced"
TYPE_PAYMENT_CANCELLED = "ar.PaymentCancelled"


register_event(TYPE_PAYMENT_RECORDED, PaymentRecordedPayload)
register_event(TYPE_PAYMENT_APPLIED, PaymentAppliedPayload)
register_event(TYPE_PAYMENT_POSTED, PaymentPostedPayload)
register_event(TYPE_PAYMENT_UNAPPLIED, PaymentUnappliedPayload)
register_event(TYPE_PAYMENT_BOUNCED, PaymentBouncedPayload)
register_event(TYPE_PAYMENT_CANCELLED, PaymentCancelledPayload)


# --- Credit notes (Phase 7.4, #112) -----------------------------------------


class CreditNoteCreatedPayload(_ARPayloadBase):
    credit_note_id: uuid.UUID
    credit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    reason: str
    total_amount: str
    state: str


class CreditNoteUpdatedPayload(_ARPayloadBase):
    credit_note_id: uuid.UUID


# --- Recurring invoice templates (Phase 7.5, #113) --------------------------
#
# PII RULE: line-level details (item descriptions, quantities, unit_price)
# carry through the payload for replay but the audit-excerpt whitelist
# strictly stays at template name + customer_id + cadence_kind. ``notes`` is
# never whitelisted.


class RecurringTemplateCreatedPayload(_ARPayloadBase):
    template_id: uuid.UUID
    name: str
    customer_id: uuid.UUID
    cadence_kind: str
    cadence_interval: int
    start_at: str
    end_at: str | None = None
    next_issue_at: str
    auto_issue: bool
    state: str
    notes: str | None = None
    discount_amount: str
    tax_amount: str
    currency: str = "USD"
    items: list[dict[str, Any]] = []


class RecurringTemplateUpdatedPayload(_ARPayloadBase):
    template_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class CreditNoteIssuedPayload(_ARPayloadBase):
    credit_note_id: uuid.UUID
    credit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    total_amount: str
    journal_entry_id: uuid.UUID


class CreditNoteAppliedPayload(_ARPayloadBase):
    credit_note_id: uuid.UUID
    credit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    amount_applied: str


class CreditNoteCancelledPayload(_ARPayloadBase):
    credit_note_id: uuid.UUID
    credit_note_number: str
    customer_id: uuid.UUID
    reversing_journal_entry_id: uuid.UUID | None = None


TYPE_CREDIT_NOTE_CREATED = "ar.CreditNoteCreated"
TYPE_CREDIT_NOTE_UPDATED = "ar.CreditNoteUpdated"
TYPE_CREDIT_NOTE_ISSUED = "ar.CreditNoteIssued"
TYPE_CREDIT_NOTE_APPLIED = "ar.CreditNoteApplied"
TYPE_CREDIT_NOTE_CANCELLED = "ar.CreditNoteCancelled"


register_event(TYPE_CREDIT_NOTE_CREATED, CreditNoteCreatedPayload)
register_event(TYPE_CREDIT_NOTE_UPDATED, CreditNoteUpdatedPayload)
register_event(TYPE_CREDIT_NOTE_ISSUED, CreditNoteIssuedPayload)
register_event(TYPE_CREDIT_NOTE_APPLIED, CreditNoteAppliedPayload)
register_event(TYPE_CREDIT_NOTE_CANCELLED, CreditNoteCancelledPayload)


# --- Debit notes (Phase 7.4, #112) ------------------------------------------


class DebitNoteCreatedPayload(_ARPayloadBase):
    debit_note_id: uuid.UUID
    debit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    reason: str
    total_amount: str
    state: str


class DebitNoteUpdatedPayload(_ARPayloadBase):
    debit_note_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class DebitNoteIssuedPayload(_ARPayloadBase):
    debit_note_id: uuid.UUID
    debit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    total_amount: str
    journal_entry_id: uuid.UUID


class DebitNoteAppliedPayload(_ARPayloadBase):
    debit_note_id: uuid.UUID
    debit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    amount_applied: str


class DebitNoteCancelledPayload(_ARPayloadBase):
    debit_note_id: uuid.UUID
    debit_note_number: str
    customer_id: uuid.UUID
    reversing_journal_entry_id: uuid.UUID | None = None


TYPE_DEBIT_NOTE_CREATED = "ar.DebitNoteCreated"
TYPE_DEBIT_NOTE_UPDATED = "ar.DebitNoteUpdated"
TYPE_DEBIT_NOTE_ISSUED = "ar.DebitNoteIssued"
TYPE_DEBIT_NOTE_APPLIED = "ar.DebitNoteApplied"
TYPE_DEBIT_NOTE_CANCELLED = "ar.DebitNoteCancelled"


register_event(TYPE_DEBIT_NOTE_CREATED, DebitNoteCreatedPayload)
register_event(TYPE_DEBIT_NOTE_UPDATED, DebitNoteUpdatedPayload)
register_event(TYPE_DEBIT_NOTE_ISSUED, DebitNoteIssuedPayload)
register_event(TYPE_DEBIT_NOTE_APPLIED, DebitNoteAppliedPayload)
register_event(TYPE_DEBIT_NOTE_CANCELLED, DebitNoteCancelledPayload)


# --- Customer credit balance (Phase 7.4, #112) -------------------------------
#
# Customer-credit accrual / application events drive the
# ``customer_credit_balance`` projection. They flow from:
# * apply_payment with excess > 0 (accrual)
# * refund posting that issues store credit (accrual; Phase 6.5 hook)
# * credit-note apply pathways once we build them
#
# The transaction_id correlates each event with its
# ``customer_credit_transaction`` row.


class CustomerCreditAccruedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: str
    source_payment_id: uuid.UUID | None = None
    source_refund_id: uuid.UUID | None = None
    source_invoice_id: uuid.UUID | None = None
    notes: str | None = None


class CustomerCreditAppliedPayload(_ARPayloadBase):
    customer_id: uuid.UUID
    transaction_id: uuid.UUID
    amount: str
    applied_to_invoice_id: uuid.UUID | None = None
    notes: str | None = None


TYPE_CUSTOMER_CREDIT_ACCRUED = "ar.CustomerCreditAccrued"
TYPE_CUSTOMER_CREDIT_APPLIED = "ar.CustomerCreditApplied"


register_event(TYPE_CUSTOMER_CREDIT_ACCRUED, CustomerCreditAccruedPayload)
register_event(TYPE_CUSTOMER_CREDIT_APPLIED, CustomerCreditAppliedPayload)
# --- Email delivery (Phase 7.7, #115) ---------------------------------------
#
# PII NOTE: ``to_address`` is carried in payloads so the event log can
# reconstruct who got mailed, but the audit excerpt MUST NOT surface it.


AGGREGATE_TYPE_EMAIL: str = "email_message"


class EmailQueuedPayload(_ARPayloadBase):
    email_id: uuid.UUID
    kind: str
    subject_kind: str | None = None
    subject_id: uuid.UUID | None = None
    to_address: str
    subject: str


class EmailSentPayload(_ARPayloadBase):
    email_id: uuid.UUID
    kind: str
    subject_kind: str | None = None
    subject_id: uuid.UUID | None = None
    provider_message_id: str | None = None
    sent_at: str


class EmailFailedPayload(_ARPayloadBase):
    email_id: uuid.UUID
    kind: str
    subject_kind: str | None = None
    subject_id: uuid.UUID | None = None
    attempts: int
    last_error: str


class EmailCancelledPayload(_ARPayloadBase):
    email_id: uuid.UUID
    kind: str


TYPE_EMAIL_QUEUED = "ar.EmailQueued"
TYPE_EMAIL_SENT = "ar.EmailSent"
TYPE_EMAIL_FAILED = "ar.EmailFailed"
TYPE_EMAIL_CANCELLED = "ar.EmailCancelled"


register_event(TYPE_EMAIL_QUEUED, EmailQueuedPayload)
register_event(TYPE_EMAIL_SENT, EmailSentPayload)
register_event(TYPE_EMAIL_FAILED, EmailFailedPayload)
register_event(TYPE_EMAIL_CANCELLED, EmailCancelledPayload)


class RecurringTemplatePausedPayload(_ARPayloadBase):
    template_id: uuid.UUID
    name: str
    customer_id: uuid.UUID
    cadence_kind: str


class RecurringTemplateResumedPayload(_ARPayloadBase):
    template_id: uuid.UUID
    name: str
    customer_id: uuid.UUID
    cadence_kind: str
    next_issue_at: str


class RecurringTemplateCancelledPayload(_ARPayloadBase):
    template_id: uuid.UUID
    name: str
    customer_id: uuid.UUID
    cadence_kind: str


class RecurringInvoiceMaterializedPayload(_ARPayloadBase):
    template_id: uuid.UUID
    name: str
    customer_id: uuid.UUID
    cadence_kind: str
    invoice_id: uuid.UUID
    invoice_number: str
    materialized_at: str
    auto_issued: bool
    next_issue_at: str | None = None


TYPE_RECURRING_TEMPLATE_CREATED = "ar.RecurringTemplateCreated"
TYPE_RECURRING_TEMPLATE_UPDATED = "ar.RecurringTemplateUpdated"
TYPE_RECURRING_TEMPLATE_PAUSED = "ar.RecurringTemplatePaused"
TYPE_RECURRING_TEMPLATE_RESUMED = "ar.RecurringTemplateResumed"
TYPE_RECURRING_TEMPLATE_CANCELLED = "ar.RecurringTemplateCancelled"
TYPE_RECURRING_INVOICE_MATERIALIZED = "ar.RecurringInvoiceMaterialized"


register_event(TYPE_RECURRING_TEMPLATE_CREATED, RecurringTemplateCreatedPayload)
register_event(TYPE_RECURRING_TEMPLATE_UPDATED, RecurringTemplateUpdatedPayload)
register_event(TYPE_RECURRING_TEMPLATE_PAUSED, RecurringTemplatePausedPayload)
register_event(TYPE_RECURRING_TEMPLATE_RESUMED, RecurringTemplateResumedPayload)
register_event(TYPE_RECURRING_TEMPLATE_CANCELLED, RecurringTemplateCancelledPayload)
register_event(TYPE_RECURRING_INVOICE_MATERIALIZED, RecurringInvoiceMaterializedPayload)
