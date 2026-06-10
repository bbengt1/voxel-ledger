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
AGGREGATE_TYPE_RECURRING_BILL_TEMPLATE: str = "recurring_bill_template"
AGGREGATE_TYPE_EXPENSE_CATEGORY: str = "expense_category"
AGGREGATE_TYPE_EXPENSE_CLAIM: str = "expense_claim"


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
    # Null in QBO replace-mode (epic #312): pushed async via the sync outbox.
    journal_entry_id: uuid.UUID | None = None


class BillPostedPayload(_APPayloadBase):
    bill_id: uuid.UUID
    bill_number: str
    journal_entry_id: uuid.UUID | None = None
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
    # Null in QBO replace-mode (epic #312): pushed async via the sync outbox.
    journal_entry_id: uuid.UUID | None = None


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


# --- Bill-payment withholding (Phase 9.7, #159) -----------------------------


class BillPaymentWithheldPayload(_APPayloadBase):
    payment_id: uuid.UUID
    payment_number: str
    application_id: uuid.UUID
    bill_id: uuid.UUID
    vendor_id: uuid.UUID
    profile_id: uuid.UUID
    profile_code: str
    rate: str
    withheld_amount: str


TYPE_BILL_PAYMENT_RECORDED = "ap.BillPaymentRecorded"
TYPE_BILL_PAYMENT_APPLIED = "ap.BillPaymentApplied"
TYPE_BILL_PAYMENT_POSTED = "ap.BillPaymentPosted"
TYPE_BILL_PAYMENT_UNAPPLIED = "ap.BillPaymentUnapplied"
TYPE_BILL_PAYMENT_BOUNCED = "ap.BillPaymentBounced"
TYPE_BILL_PAYMENT_CANCELLED = "ap.BillPaymentCancelled"
TYPE_BILL_PAYMENT_WITHHELD = "ap.BillPaymentWithheld"


register_event(TYPE_BILL_PAYMENT_RECORDED, BillPaymentRecordedPayload)
register_event(TYPE_BILL_PAYMENT_APPLIED, BillPaymentAppliedPayload)
register_event(TYPE_BILL_PAYMENT_POSTED, BillPaymentPostedPayload)
register_event(TYPE_BILL_PAYMENT_UNAPPLIED, BillPaymentUnappliedPayload)
register_event(TYPE_BILL_PAYMENT_BOUNCED, BillPaymentBouncedPayload)
register_event(TYPE_BILL_PAYMENT_CANCELLED, BillPaymentCancelledPayload)
register_event(TYPE_BILL_PAYMENT_WITHHELD, BillPaymentWithheldPayload)


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


# --- Recurring bill templates (Phase 8.5, #132) -----------------------------
#
# PII RULE: line-level details (item descriptions, quantities, unit_price)
# carry through the payload for replay but the audit-excerpt whitelist
# strictly stays at template name + vendor_id + cadence_kind. ``notes`` is
# never whitelisted.


class RecurringBillTemplateCreatedPayload(_APPayloadBase):
    template_id: uuid.UUID
    name: str
    vendor_id: uuid.UUID
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


class RecurringBillTemplateUpdatedPayload(_APPayloadBase):
    template_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class RecurringBillTemplatePausedPayload(_APPayloadBase):
    template_id: uuid.UUID
    name: str
    vendor_id: uuid.UUID
    cadence_kind: str


class RecurringBillTemplateResumedPayload(_APPayloadBase):
    template_id: uuid.UUID
    name: str
    vendor_id: uuid.UUID
    cadence_kind: str
    next_issue_at: str


class RecurringBillTemplateCancelledPayload(_APPayloadBase):
    template_id: uuid.UUID
    name: str
    vendor_id: uuid.UUID
    cadence_kind: str


class RecurringBillMaterializedPayload(_APPayloadBase):
    template_id: uuid.UUID
    name: str
    vendor_id: uuid.UUID
    cadence_kind: str
    bill_id: uuid.UUID
    bill_number: str
    materialized_at: str
    auto_issued: bool
    next_issue_at: str | None = None


TYPE_RECURRING_BILL_TEMPLATE_CREATED = "ap.RecurringBillTemplateCreated"
TYPE_RECURRING_BILL_TEMPLATE_UPDATED = "ap.RecurringBillTemplateUpdated"
TYPE_RECURRING_BILL_TEMPLATE_PAUSED = "ap.RecurringBillTemplatePaused"
TYPE_RECURRING_BILL_TEMPLATE_RESUMED = "ap.RecurringBillTemplateResumed"
TYPE_RECURRING_BILL_TEMPLATE_CANCELLED = "ap.RecurringBillTemplateCancelled"
TYPE_RECURRING_BILL_MATERIALIZED = "ap.RecurringBillMaterialized"


register_event(TYPE_RECURRING_BILL_TEMPLATE_CREATED, RecurringBillTemplateCreatedPayload)
register_event(TYPE_RECURRING_BILL_TEMPLATE_UPDATED, RecurringBillTemplateUpdatedPayload)
register_event(TYPE_RECURRING_BILL_TEMPLATE_PAUSED, RecurringBillTemplatePausedPayload)
register_event(TYPE_RECURRING_BILL_TEMPLATE_RESUMED, RecurringBillTemplateResumedPayload)
register_event(TYPE_RECURRING_BILL_TEMPLATE_CANCELLED, RecurringBillTemplateCancelledPayload)
register_event(TYPE_RECURRING_BILL_MATERIALIZED, RecurringBillMaterializedPayload)


# --- Expense categories (Phase 8.6, #133) -----------------------------------
#
# PII RULE: ``notes`` is a free-form operator field and MUST NEVER be
# whitelisted into audit excerpts. The payload carries it for replay; the
# audit denormalization strictly limits itself to ``code`` + ``name``.


class ExpenseCategoryCreatedPayload(_APPayloadBase):
    expense_category_id: uuid.UUID
    code: str
    name: str
    default_expense_account_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    is_active: bool
    notes: str | None = None


class ExpenseCategoryUpdatedPayload(_APPayloadBase):
    expense_category_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class ExpenseCategoryArchivedPayload(_APPayloadBase):
    expense_category_id: uuid.UUID
    code: str
    name: str


TYPE_EXPENSE_CATEGORY_CREATED = "ap.ExpenseCategoryCreated"
TYPE_EXPENSE_CATEGORY_UPDATED = "ap.ExpenseCategoryUpdated"
TYPE_EXPENSE_CATEGORY_ARCHIVED = "ap.ExpenseCategoryArchived"


register_event(TYPE_EXPENSE_CATEGORY_CREATED, ExpenseCategoryCreatedPayload)
register_event(TYPE_EXPENSE_CATEGORY_UPDATED, ExpenseCategoryUpdatedPayload)
register_event(TYPE_EXPENSE_CATEGORY_ARCHIVED, ExpenseCategoryArchivedPayload)


# --- Expense claims (Phase 8.7, #134) ---------------------------------------
#
# PII RULE: line ``description``, ``notes``, and ``rejection_reason`` are
# carried in the payload so the event log can reconstruct the row but the
# audit-excerpt whitelist NEVER surfaces them. Audit excerpts are limited
# to claim_number, submitter_user_id, state, and total_amount.


class ExpenseClaimCreatedPayload(_APPayloadBase):
    expense_claim_id: uuid.UUID
    claim_number: str
    submitter_user_id: uuid.UUID
    state: str
    total_amount: str
    currency: str = "USD"
    notes: str | None = None
    lines: list[dict[str, Any]] = []


class ExpenseClaimUpdatedPayload(_APPayloadBase):
    expense_claim_id: uuid.UUID
    before: dict[str, Any]
    after: dict[str, Any]


class ExpenseClaimSubmittedPayload(_APPayloadBase):
    expense_claim_id: uuid.UUID
    claim_number: str
    submitter_user_id: uuid.UUID
    total_amount: str
    approval_request_id: uuid.UUID | None = None


class ExpenseClaimApprovedPayload(_APPayloadBase):
    expense_claim_id: uuid.UUID
    claim_number: str
    submitter_user_id: uuid.UUID
    approver_user_id: uuid.UUID
    total_amount: str
    # None in QBO replace-mode (epic #312): pushed async via the sync outbox.
    journal_entry_id: uuid.UUID | None = None


class ExpenseClaimRejectedPayload(_APPayloadBase):
    expense_claim_id: uuid.UUID
    claim_number: str
    submitter_user_id: uuid.UUID
    approver_user_id: uuid.UUID
    rejection_reason: str | None = None


class ExpenseClaimReimbursedPayload(_APPayloadBase):
    expense_claim_id: uuid.UUID
    claim_number: str
    submitter_user_id: uuid.UUID
    bill_payment_id: uuid.UUID


class ExpenseClaimCancelledPayload(_APPayloadBase):
    expense_claim_id: uuid.UUID
    claim_number: str
    submitter_user_id: uuid.UUID


TYPE_EXPENSE_CLAIM_CREATED = "ap.ExpenseClaimCreated"
TYPE_EXPENSE_CLAIM_UPDATED = "ap.ExpenseClaimUpdated"
TYPE_EXPENSE_CLAIM_SUBMITTED = "ap.ExpenseClaimSubmitted"
TYPE_EXPENSE_CLAIM_APPROVED = "ap.ExpenseClaimApproved"
TYPE_EXPENSE_CLAIM_REJECTED = "ap.ExpenseClaimRejected"
TYPE_EXPENSE_CLAIM_REIMBURSED = "ap.ExpenseClaimReimbursed"
TYPE_EXPENSE_CLAIM_CANCELLED = "ap.ExpenseClaimCancelled"


register_event(TYPE_EXPENSE_CLAIM_CREATED, ExpenseClaimCreatedPayload)
register_event(TYPE_EXPENSE_CLAIM_UPDATED, ExpenseClaimUpdatedPayload)
register_event(TYPE_EXPENSE_CLAIM_SUBMITTED, ExpenseClaimSubmittedPayload)
register_event(TYPE_EXPENSE_CLAIM_APPROVED, ExpenseClaimApprovedPayload)
register_event(TYPE_EXPENSE_CLAIM_REJECTED, ExpenseClaimRejectedPayload)
register_event(TYPE_EXPENSE_CLAIM_REIMBURSED, ExpenseClaimReimbursedPayload)
register_event(TYPE_EXPENSE_CLAIM_CANCELLED, ExpenseClaimCancelledPayload)


# --- Billable expenses (Phase 8.8, #135) ------------------------------------
#
# Operator flags a ``bill_item`` or ``expense_claim_line`` as
# ``is_billable`` with a target ``customer_id``; later the invoice composer
# pulls those unbilled rows + appends them as invoice lines with a markup.
# Once linked, the source's ``billed_invoice_item_id`` is stamped so it
# can't be re-billed. The link is emitted with ``aggregate_type=invoice``
# because the invoice composer is the actor — replay rebuilding the
# invoice naturally sees the link event in the invoice aggregate stream.


class BillableExpenseLinkedPayload(_APPayloadBase):
    source_kind: str  # "bill_item" | "expense_claim_line"
    source_id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_item_id: uuid.UUID
    customer_id: uuid.UUID
    amount: str  # billed (after markup)
    source_amount: str  # before markup
    markup_percent: str


TYPE_BILLABLE_EXPENSE_LINKED = "ap.BillableExpenseLinked"

register_event(TYPE_BILLABLE_EXPENSE_LINKED, BillableExpenseLinkedPayload)
