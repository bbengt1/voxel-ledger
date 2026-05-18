"""Per-event-type whitelist of payload fields safe to denormalize.

The ``audit_log.payload_excerpt`` column carries a tiny subset of each
event's payload so the audit query API can show "what happened" without
joining back to the event log on every read.

The whitelist is a hard contract: **no excerpt unless explicitly opted in**.
Sensitive fields (password, password_hash, token, token_hash, refresh_token,
session_id) MUST NEVER appear in an excerpt, regardless of event type.

The auth-event whitelist only allows ``email``. Tokens and hashes never
appear in auth payloads at all (see ``app/events/types/auth.py``), but the
deny-list below is a belt-and-suspenders check.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.events.types import accounting as accounting_events
from app.events.types import ap as ap_events
from app.events.types import approvals as approvals_events
from app.events.types import ar as ar_events
from app.events.types import auth as auth_events
from app.events.types import banking as banking_events
from app.events.types import catalog as catalog_events
from app.events.types import custom_fields as cf_events
from app.events.types import inventory as inventory_events
from app.events.types import notes_attachments as notes_events
from app.events.types import production as production_events
from app.events.types import sales as sales_events
from app.events.types import users as users_events

# Event type → tuple of allowed payload field names. Empty/absent = no
# excerpt at all.
_WHITELIST: dict[str, tuple[str, ...]] = {}

# Optional per-(event_type, field) post-processor that rewrites the
# excerpt value. Used by event types that need to summarize a bulky
# field (e.g. a list of journal lines → count + totals) rather than
# verbatim-copy it. The transformer receives the FULL payload so it can
# compute summaries that span multiple raw fields and returns the value
# to store under that excerpt key. Returning ``None`` drops the field.
ExcerptTransformer = Callable[[dict[str, Any]], Any]
_TRANSFORMERS: dict[tuple[str, str], ExcerptTransformer] = {}

# Field names that MUST NEVER appear in an excerpt, regardless of whether
# they were whitelisted. Belt-and-suspenders defense against a typo in the
# whitelist letting a secret through.
_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "password_hash",
        "passwordhash",
        "token",
        "token_hash",
        "tokenhash",
        "refresh_token",
        "access_token",
        "session_id",
        "secret",
    }
)


def register_excerpt_fields(event_type: str, fields: tuple[str, ...]) -> None:
    """Declare which payload fields are safe to denormalize for ``event_type``.

    A field listed in the global forbidden set is rejected loudly at
    registration so this can't be ignored at runtime.
    """
    for field in fields:
        if field.lower() in _FORBIDDEN_FIELDS:
            raise ValueError(
                f"refusing to whitelist forbidden field {field!r} for event type {event_type!r}"
            )
    _WHITELIST[event_type] = tuple(fields)


def register_excerpt_transformer(event_type: str, field: str, fn: ExcerptTransformer) -> None:
    """Attach a transformer for a single excerpt field.

    The transformer fires whenever ``compute_excerpt`` would emit
    ``field`` for ``event_type``; it replaces the raw payload value. If
    the transformer returns ``None`` the field is dropped from the
    excerpt entirely.

    The ``field`` itself must still be in the whitelist registered via
    :func:`register_excerpt_fields`. We keep the whitelist as the
    single source of truth for "what's in the excerpt"; transformers
    only rewrite the value.
    """
    _TRANSFORMERS[(event_type, field)] = fn


def compute_excerpt(event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the excerpt dict for ``event_type``, or ``None`` if no
    whitelist is registered (deny by default).

    Forbidden fields are filtered defensively even if (somehow) they
    appeared in a whitelisted set — that path is unreachable today
    because ``register_excerpt_fields`` blocks the registration, but the
    second check guarantees the invariant at the read-model boundary.
    """
    fields = _WHITELIST.get(event_type)
    if not fields:
        return None
    excerpt: dict[str, Any] = {}
    for field in fields:
        if field.lower() in _FORBIDDEN_FIELDS:
            continue
        transformer = _TRANSFORMERS.get((event_type, field))
        if transformer is not None:
            value = transformer(payload)
            if value is not None:
                excerpt[field] = value
        elif field in payload:
            excerpt[field] = payload[field]
    return excerpt or None


# ---------------------------------------------------------------------------
# Auth-event whitelists (Phase 1.4).
# ---------------------------------------------------------------------------
# Only ``email`` is denormalized. Never password/token/hash.

_EMAIL_ONLY: tuple[str, ...] = ("email",)

register_excerpt_fields(auth_events.TYPE_LOGIN_SUCCEEDED, _EMAIL_ONLY)
register_excerpt_fields(auth_events.TYPE_LOGIN_FAILED, _EMAIL_ONLY)
register_excerpt_fields(auth_events.TYPE_LOGIN_INACTIVE, _EMAIL_ONLY)
# Refresh / logout / family-revoked / rate-limited carry no email — no excerpt.


# ---------------------------------------------------------------------------
# Users-admin event whitelists (Phase 1.6).
# ---------------------------------------------------------------------------
# Never whitelist anything password-shaped; the global forbidden set
# (password, password_hash, token, ...) is enforced at register time as a
# belt-and-suspenders defense.

register_excerpt_fields(users_events.TYPE_USER_CREATED, ("email", "full_name", "role"))
register_excerpt_fields(users_events.TYPE_USER_UPDATED, ("before", "after"))
register_excerpt_fields(users_events.TYPE_USER_DEACTIVATED, ("reason",))
# Reactivated + password-reset-by-admin carry only ids — no excerpt is useful.


# ---------------------------------------------------------------------------
# Catalog event whitelists (Phase 2.1).
# ---------------------------------------------------------------------------
# Materials carry identifying metadata only — no sensitive content.

register_excerpt_fields(
    catalog_events.TYPE_MATERIAL_CREATED,
    ("name", "brand", "material_type", "color"),
)
register_excerpt_fields(
    catalog_events.TYPE_MATERIAL_UPDATED,
    ("before", "after"),
)
# Archive/unarchive carry only the material_id — no excerpt is useful.


# --- Products (Phase 2.3) -------------------------------------------------
# Whitelist sku/name/category. ``description`` is intentionally NOT
# whitelisted — free-form text that's better kept out of the audit log.
# ``old_price`` / ``new_price`` are explicitly whitelisted for the
# dedicated ProductPriceChanged event so downstream history readers can
# render the change without rejoining the full event payload.

register_excerpt_fields(
    catalog_events.TYPE_PRODUCT_CREATED,
    ("sku", "name", "category"),
)
register_excerpt_fields(
    catalog_events.TYPE_PRODUCT_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    catalog_events.TYPE_PRODUCT_PRICE_CHANGED,
    ("old_price", "new_price"),
)

# --- BOM (Phase 2.4) ----------------------------------------------------

register_excerpt_fields(
    catalog_events.TYPE_BOM_COMPONENT_ADDED,
    ("parent_product_id", "component_kind", "component_id", "quantity"),
)
register_excerpt_fields(
    catalog_events.TYPE_BOM_COMPONENT_REMOVED,
    ("parent_product_id", "component_kind", "component_id"),
)
register_excerpt_fields(
    catalog_events.TYPE_BOM_COMPONENT_QUANTITY_CHANGED,
    ("parent_product_id", "old_quantity", "new_quantity"),
)
register_excerpt_fields(
    catalog_events.TYPE_PRODUCT_COST_CHANGED,
    ("product_id", "old_cost", "new_cost"),
)
# ProductArchived / ProductUnarchived carry only the product_id — no
# excerpt is useful.


# ---------------------------------------------------------------------------
# Inventory event whitelists (Phase 2.1).
# ---------------------------------------------------------------------------
# ``notes`` is intentionally NOT whitelisted: it's free-text and might
# contain vendor account numbers or other sensitive payment data.

register_excerpt_fields(
    inventory_events.TYPE_MATERIAL_RECEIVED,
    ("material_id", "grams", "total_cost"),
)


# --- Inventory locations (Phase 3.1) ---

register_excerpt_fields(
    inventory_events.TYPE_LOCATION_CREATED,
    ("name", "code", "kind"),
)
register_excerpt_fields(
    inventory_events.TYPE_LOCATION_UPDATED,
    ("before", "after"),
)
# LocationArchived / LocationUnarchived carry only the location_id — no
# excerpt is useful.


# --- Inventory transactions (Phase 3.2) ---
# ``unit_cost`` / ``total_cost`` are intentionally NOT whitelisted — the
# spec keeps cost out of the audit denormalization (the cost columns
# live on the inventory_transaction row itself if a reader needs them).

register_excerpt_fields(
    inventory_events.TYPE_TRANSACTION_RECORDED,
    ("kind", "entity_kind", "entity_id", "location_id", "signed_quantity", "reason"),
)


# ---------------------------------------------------------------------------
# Catalog: Supplies (Phase 2.2)
# ---------------------------------------------------------------------------
# Identifying metadata only — no sensitive content.

register_excerpt_fields(
    catalog_events.TYPE_SUPPLY_CREATED,
    ("name", "unit", "unit_cost", "vendor"),
)
register_excerpt_fields(
    catalog_events.TYPE_SUPPLY_UPDATED,
    ("before", "after"),
)
# Archive/unarchive carry only the supply_id — no excerpt is useful.


# ---------------------------------------------------------------------------
# Catalog: Rates (Phase 2.2)
# ---------------------------------------------------------------------------
# Rates are configuration knobs; no sensitive content.

register_excerpt_fields(
    catalog_events.TYPE_RATE_CREATED,
    ("name", "kind", "value", "is_default_for_kind"),
)
register_excerpt_fields(
    catalog_events.TYPE_RATE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    catalog_events.TYPE_RATE_DEFAULTED,
    ("kind", "previous_default_rate_id"),
)
# Archive/unarchive carry only the rate_id — no excerpt is useful.


# --- Custom fields / form templates (Phase 2.5) ---

register_excerpt_fields(
    cf_events.TYPE_CUSTOM_FIELD_CREATED,
    ("entity_type", "key", "label", "field_type", "required"),
)
register_excerpt_fields(
    cf_events.TYPE_CUSTOM_FIELD_UPDATED,
    ("before", "after"),
)
# Archive / unarchive carry only the custom_field_id — no excerpt useful.

register_excerpt_fields(
    cf_events.TYPE_FORM_TEMPLATE_CREATED,
    ("entity_type", "name"),
)
register_excerpt_fields(
    cf_events.TYPE_FORM_TEMPLATE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    cf_events.TYPE_FORM_TEMPLATE_DEFAULTED,
    ("entity_type", "previous_default_template_id"),
)
register_excerpt_fields(
    cf_events.TYPE_FORM_TEMPLATE_FIELD_ADDED,
    ("custom_field_id", "display_order"),
)
register_excerpt_fields(
    cf_events.TYPE_FORM_TEMPLATE_FIELD_REMOVED,
    ("custom_field_id",),
)


# ---------------------------------------------------------------------------
# Notes & attachments (Phase 2.6).
# ---------------------------------------------------------------------------
# Per-event excerpt strategy:
# * Note bodies are NEVER whitelisted in full. We whitelist the
#   ``body_preview`` field (max 100 chars, sliced by the service before
#   emitting the event) and the polymorphic ref. The full body lives only
#   on the ``note`` row + as the inputs to the body_preview function — it
#   is not in the event payload at all.
# * Attachments whitelist identity metadata only. We NEVER whitelist
#   ``storage_path`` — it is a private internal detail of the attachments
#   service and could leak filesystem layout to viewers.

register_excerpt_fields(
    notes_events.TYPE_NOTE_CREATED,
    ("entity_kind", "entity_id", "author_user_id", "body_preview"),
)
register_excerpt_fields(
    notes_events.TYPE_NOTE_UPDATED,
    ("body_preview_before", "body_preview_after"),
)
register_excerpt_fields(
    notes_events.TYPE_NOTE_DELETED,
    ("entity_kind", "entity_id"),
)
# Pin / unpin carry only the note_id — no excerpt is useful.

register_excerpt_fields(
    notes_events.TYPE_ATTACHMENT_UPLOADED,
    ("entity_kind", "entity_id", "filename", "mime_type", "byte_size"),
)
# AttachmentArchived carries only the attachment_id.


# --- Accounting: accounts (Phase 4.1) ---

register_excerpt_fields(
    accounting_events.TYPE_ACCOUNT_CREATED,
    ("code", "name", "type", "parent_account_id"),
)
register_excerpt_fields(
    accounting_events.TYPE_ACCOUNT_UPDATED,
    ("before", "after"),
)
# Archive / unarchive carry only the account_id — no excerpt useful.


# --- Accounting: journal entries (Phase 4.2) ---
#
# Lines are intentionally NOT denormalized verbatim — an entry could
# carry 30+ lines, which would bloat the audit log. Instead we surface
# a ``lines`` summary built by a transformer: ``{count, total_debit,
# total_credit}``.

from decimal import Decimal  # noqa: E402


def _journal_lines_summary(payload: dict[str, Any]) -> dict[str, Any]:
    lines = payload.get("lines") or []
    total_d = Decimal("0")
    total_c = Decimal("0")
    for line in lines:
        try:
            total_d += Decimal(str(line.get("debit", "0")))
            total_c += Decimal(str(line.get("credit", "0")))
        except (ArithmeticError, ValueError):
            continue
    return {
        "count": len(lines),
        "total_debit": str(total_d),
        "total_credit": str(total_c),
    }


register_excerpt_fields(
    accounting_events.TYPE_JOURNAL_ENTRY_POSTED,
    ("entry_number", "description", "actor_user_id", "posted_at", "lines"),
)
register_excerpt_transformer(
    accounting_events.TYPE_JOURNAL_ENTRY_POSTED, "lines", _journal_lines_summary
)
register_excerpt_fields(
    accounting_events.TYPE_JOURNAL_ENTRY_REVERSED,
    ("original_entry_id", "reversal_entry_id", "reversal_entry_number"),
)


# --- Accounting: periods (Phase 4.3) ---

register_excerpt_fields(
    accounting_events.TYPE_PERIOD_CREATED,
    ("name", "start_date", "end_date"),
)
register_excerpt_fields(
    accounting_events.TYPE_PERIOD_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    accounting_events.TYPE_PERIOD_CLOSED,
    ("closed_by_user_id",),
)
register_excerpt_fields(
    accounting_events.TYPE_PERIOD_REOPENED,
    ("reopened_by_user_id",),
)
register_excerpt_fields(
    accounting_events.TYPE_PERIOD_LOCKED,
    ("locked_by_user_id",),
)


# --- Approvals (Phase 4.4) ---
#
# Critical: ``payload`` is NEVER whitelisted. The approval-request row
# carries the full proposed mutation — a journal entry, a refund, etc. —
# which could contain sensitive content (counterparty info, free-text
# memos, etc.). Only the short ``payload_summary`` (~100 chars, built
# by the service from request_type + subject_kind) is allowed through.
# A regression test in test_approvals_payload_not_leaked_to_audit.py
# guards this invariant.

register_excerpt_fields(
    approvals_events.TYPE_APPROVAL_REQUESTED,
    (
        "request_type",
        "subject_kind",
        "subject_id",
        "requested_by_user_id",
        "threshold_amount",
        "payload_summary",
    ),
)
register_excerpt_fields(
    approvals_events.TYPE_APPROVAL_APPROVED,
    ("approver_user_id", "decision_note_preview"),
)
register_excerpt_fields(
    approvals_events.TYPE_APPROVAL_REJECTED,
    ("approver_user_id", "decision_note_preview"),
)
register_excerpt_fields(
    approvals_events.TYPE_APPROVAL_CANCELLED,
    ("cancelled_by_user_id",),
)


# --- Accounting: divisions + budgets (Phase 4.5) ---

register_excerpt_fields(
    accounting_events.TYPE_DIVISION_CREATED,
    ("name", "code"),
)
register_excerpt_fields(
    accounting_events.TYPE_DIVISION_UPDATED,
    ("before", "after"),
)
# DivisionArchived / DivisionUnarchived carry only the division_id — no
# excerpt is useful.

register_excerpt_fields(
    accounting_events.TYPE_BUDGET_SET,
    ("account_id", "division_id", "period_id", "old_amount", "new_amount"),
)
register_excerpt_fields(
    accounting_events.TYPE_BUDGET_UNSET,
    ("account_id", "division_id", "period_id"),
)


# ---------------------------------------------------------------------------
# Production: printers + cameras (Phase 5.1)
# ---------------------------------------------------------------------------
#
# CRITICAL: ``moonraker_api_key`` and ``password_secret`` MUST NEVER be
# whitelisted here. They are the only secret-shaped fields on the
# printer + camera aggregates. The service layer replaces them with
# the sentinel ``"***"`` before emitting any event, so a slip in the
# whitelist below still couldn't surface the real value — but we keep
# the whitelist narrow as belt-and-suspenders. A regression test
# (test_printers_secrets_never_leak.py) guards this invariant.

register_excerpt_fields(
    production_events.TYPE_PRINTER_CREATED,
    ("name", "slug", "printer_type"),
)
register_excerpt_fields(
    production_events.TYPE_PRINTER_UPDATED,
    ("before", "after"),
)
# PrinterArchived / PrinterUnarchived carry only the printer_id — no
# excerpt is useful.

register_excerpt_fields(
    production_events.TYPE_CAMERA_CONFIGURED,
    ("printer_id", "kind", "snapshot_url"),
)
register_excerpt_fields(
    production_events.TYPE_CAMERA_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    production_events.TYPE_CAMERA_DELETED,
    ("printer_id",),
)


# ---------------------------------------------------------------------------
# Production: jobs + plates (Phase 5.2)
# ---------------------------------------------------------------------------

register_excerpt_fields(
    production_events.TYPE_JOB_CREATED,
    ("job_number", "product_id"),
)
register_excerpt_fields(
    production_events.TYPE_JOB_UPDATED,
    ("before", "after"),
)
# Job submit/start/complete/cancel carry only ``job_id`` — no excerpt
# beyond the aggregate ID itself is useful.
register_excerpt_fields(
    production_events.TYPE_PLATE_ASSIGNED,
    ("plate_id", "printer_id"),
)
register_excerpt_fields(
    production_events.TYPE_PLATE_UNASSIGNED,
    ("plate_id", "printer_id"),
)
register_excerpt_fields(
    production_events.TYPE_PLATE_RUN_RECORDED,
    ("plate_id", "new_runs_completed"),
)


# --- Production: printer history (Phase 5.4) ---
#
# ``details`` is intentionally NOT whitelisted — it's the monitor's
# free-form scratch payload (current filename, progress, error message)
# and could contain user-supplied gcode names. Audit readers get just
# the structural fields.

register_excerpt_fields(
    production_events.TYPE_PRINTER_HISTORY_EVENT_RECORDED,
    ("printer_id", "event_kind", "occurred_at"),
)


# ---------------------------------------------------------------------------
# Production: production orders (Phase 5.5)
# ---------------------------------------------------------------------------

register_excerpt_fields(
    production_events.TYPE_PRODUCTION_ORDER_CREATED,
    ("order_number", "name", "state", "priority"),
)
register_excerpt_fields(
    production_events.TYPE_PRODUCTION_ORDER_UPDATED,
    ("before", "after"),
)
# Activated / Completed / Archived carry only the production_order_id —
# no excerpt beyond the aggregate ID itself is useful.
register_excerpt_fields(
    production_events.TYPE_JOB_ADDED_TO_ORDER,
    ("job_id", "display_order"),
)
register_excerpt_fields(
    production_events.TYPE_JOB_REMOVED_FROM_ORDER,
    ("job_id",),
)


# ---------------------------------------------------------------------------
# Sales: channels (Phase 6.1)
# ---------------------------------------------------------------------------
#
# Fee percentages, flat fees, and account references are configuration
# metadata — denormalizing them into the audit excerpt is exactly what
# we want for later "what changed?" UIs. ``external_id_format_hint`` is
# operator-provided free-form text but is bounded (regex / example) and
# safe to surface.

register_excerpt_fields(
    sales_events.TYPE_SALES_CHANNEL_CREATED,
    (
        "name",
        "slug",
        "kind",
        "fee_model",
        "fee_percent",
        "fee_flat",
        "external_id_format_hint",
    ),
)
register_excerpt_fields(
    sales_events.TYPE_SALES_CHANNEL_UPDATED,
    ("before", "after"),
)
# Archived / Unarchived carry only the sales_channel_id — no excerpt is
# useful.


# ---------------------------------------------------------------------------
# Sales: sales (Phase 6.2)
# ---------------------------------------------------------------------------
#
# CRITICAL: ``customer_email`` and ``notes`` MUST NEVER be whitelisted —
# they are PII / operator free-text and the spec forbids surfacing them
# in the audit denormalization. The whitelist intentionally stays narrow:
# channel_id, sale_number, total_amount only on Created/Confirmed; the
# diff fields on Updated; sale_number on Fulfilled/Cancelled.

register_excerpt_fields(
    sales_events.TYPE_SALE_CREATED,
    ("sale_number", "channel_id", "total_amount"),
)
register_excerpt_fields(
    sales_events.TYPE_SALE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    sales_events.TYPE_SALE_CONFIRMED,
    ("sale_number", "channel_id", "total_amount"),
)
register_excerpt_fields(
    sales_events.TYPE_SALE_FULFILLED,
    ("sale_number",),
)
register_excerpt_fields(
    sales_events.TYPE_SALE_CANCELLED,
    ("sale_number",),
)
# Phase 6.3 (#95): SalePosted / SaleReversed carry sale_number + ID
# references for audit traceability. No customer data ever lands in
# these payloads.
register_excerpt_fields(
    sales_events.TYPE_SALE_POSTED,
    ("sale_number", "journal_entry_id", "total_amount"),
)
register_excerpt_fields(
    sales_events.TYPE_SALE_REVERSED,
    (
        "sale_number",
        "reversing_journal_entry_id",
        "original_journal_entry_id",
    ),
)


# --- Sales: refunds (Phase 6.5) ---
#
# CRITICAL: ``notes`` and any customer-email-shaped field MUST NEVER be
# whitelisted here. Refund payloads carry the operator's free-text notes
# (needed for replay) but those are never surfaced in the audit
# denormalization.
register_excerpt_fields(
    sales_events.TYPE_REFUND_CREATED,
    ("refund_number", "sale_id", "total_amount", "reason_code"),
)
register_excerpt_fields(
    sales_events.TYPE_REFUND_APPROVED,
    ("refund_number", "sale_id", "total_amount", "reason_code"),
)
register_excerpt_fields(
    sales_events.TYPE_REFUND_REJECTED,
    ("refund_number", "sale_id"),
)
register_excerpt_fields(
    sales_events.TYPE_REFUND_POSTED,
    ("refund_number", "sale_id", "total_amount", "reason_code"),
)
register_excerpt_fields(
    sales_events.TYPE_REFUND_CANCELLED,
    ("refund_number", "sale_id"),
)


# ---------------------------------------------------------------------------
# Sales: POS carts (Phase 6.4)
# ---------------------------------------------------------------------------
#
# CRITICAL: ``customer_email`` MUST NEVER be whitelisted — POS receipts may
# capture an email at checkout but it never reaches the audit denorm. Only
# structural identifiers + totals surface here.

register_excerpt_fields(
    sales_events.TYPE_POS_CART_OPENED,
    ("cart_id", "channel_id"),
)
register_excerpt_fields(
    sales_events.TYPE_POS_LINE_ADDED,
    ("cart_id", "line_number"),
)
register_excerpt_fields(
    sales_events.TYPE_POS_LINE_UPDATED,
    ("cart_id", "line_number"),
)
register_excerpt_fields(
    sales_events.TYPE_POS_LINE_REMOVED,
    ("cart_id", "line_number"),
)
register_excerpt_fields(
    sales_events.TYPE_POS_CART_CHECKED_OUT,
    ("cart_id", "channel_id", "total"),
)
register_excerpt_fields(
    sales_events.TYPE_POS_CART_VOIDED,
    ("cart_id",),
)


# --- Sales: shipments (Phase 6.6, #98) ----------------------------------
#
# CRITICAL: ``ship_to``, ``ship_from``, and ``label_pdf_storage_key`` MUST
# NEVER be whitelisted — the destination address is PII and the storage
# key is a private internal handle. The whitelist intentionally stays
# narrow: carrier, service_level, tracking_number, cost_amount + IDs.

register_excerpt_fields(
    sales_events.TYPE_SHIPPING_LABEL_PURCHASED,
    (
        "shipment_id",
        "sale_id",
        "carrier",
        "service_level",
        "tracking_number",
        "cost_amount",
    ),
)
register_excerpt_fields(
    sales_events.TYPE_SHIPMENT_SHIPPED,
    ("shipment_id", "sale_id", "carrier", "tracking_number"),
)
register_excerpt_fields(
    sales_events.TYPE_SHIPMENT_DELIVERED,
    ("shipment_id", "sale_id", "carrier", "tracking_number"),
)
register_excerpt_fields(
    sales_events.TYPE_SHIPMENT_CANCELLED,
    ("shipment_id", "sale_id", "carrier", "void_requested"),
)


# ---------------------------------------------------------------------------
# AR: customers (Phase 7.1, #109)
# ---------------------------------------------------------------------------
#
# CRITICAL PII RULE: ``primary_email``, ``phone``, ``billing_address``,
# ``shipping_address``, and ``notes`` MUST NEVER be whitelisted here.
# The payload carries them so replay can reconstruct the customer row,
# but the audit denormalization keeps strictly to ``customer_number`` +
# ``display_name``. A regression test in
# ``tests/test_customers_pii_audit.py`` guards the invariant.

register_excerpt_fields(
    ar_events.TYPE_CUSTOMER_CREATED,
    ("customer_number", "display_name"),
)
register_excerpt_fields(
    ar_events.TYPE_CUSTOMER_UPDATED,
    ("before", "after"),
)
# Archived / Unarchived carry only the customer_id — no excerpt is useful.
register_excerpt_fields(
    ar_events.TYPE_CUSTOMER_CONTACT_ADDED,
    ("contact_id", "role_label", "is_primary"),
)
register_excerpt_fields(
    ar_events.TYPE_CUSTOMER_CONTACT_UPDATED,
    ("contact_id", "before", "after"),
)
register_excerpt_fields(
    ar_events.TYPE_CUSTOMER_CONTACT_REMOVED,
    ("contact_id",),
)


# ---------------------------------------------------------------------------
# AR: quotes (Phase 7.2, #110)
# ---------------------------------------------------------------------------
#
# PII RULE: ``notes`` (operator free-text) and ``billing_address_snapshot``
# MUST NEVER be whitelisted here. The payload carries them so replay can
# reconstruct the quote, but the audit denormalization keeps strictly to
# ``quote_number``, ``customer_id``, and ``total_amount``. A regression
# test in ``tests/test_quotes_events.py`` guards the invariant.

register_excerpt_fields(
    ar_events.TYPE_QUOTE_CREATED,
    ("quote_number", "customer_id", "total_amount"),
)
register_excerpt_fields(
    ar_events.TYPE_QUOTE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ar_events.TYPE_QUOTE_SENT,
    ("quote_number", "customer_id", "total_amount"),
)
register_excerpt_fields(
    ar_events.TYPE_QUOTE_ACCEPTED,
    ("quote_number", "customer_id", "total_amount"),
)
register_excerpt_fields(
    ar_events.TYPE_QUOTE_DECLINED,
    ("quote_number", "customer_id"),
)
register_excerpt_fields(
    ar_events.TYPE_QUOTE_EXPIRED,
    ("quote_number", "customer_id"),
)
register_excerpt_fields(
    ar_events.TYPE_QUOTE_CANCELLED,
    ("quote_number", "customer_id"),
)
register_excerpt_fields(
    ar_events.TYPE_QUOTE_CONVERTED_TO_INVOICE,
    ("quote_number", "customer_id", "invoice_id", "total_amount"),
)


# ---------------------------------------------------------------------------
# AR: invoices (Phase 7.3, #111)
# ---------------------------------------------------------------------------
#
# PII RULE: ``notes`` and ``billing_address_snapshot`` MUST NEVER be
# whitelisted here. The payload carries them so replay can reconstruct
# the invoice, but the audit denormalization keeps strictly to
# ``invoice_number``, ``customer_id``, ``total_amount``, and ``due_at``.

register_excerpt_fields(
    ar_events.TYPE_INVOICE_CREATED,
    ("invoice_number", "customer_id", "total_amount", "due_at"),
)
register_excerpt_fields(
    ar_events.TYPE_INVOICE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ar_events.TYPE_INVOICE_ISSUED,
    (
        "invoice_number",
        "customer_id",
        "total_amount",
        "due_at",
        "journal_entry_id",
    ),
)
register_excerpt_fields(
    ar_events.TYPE_INVOICE_POSTED,
    ("invoice_number", "journal_entry_id", "total_amount"),
)
register_excerpt_fields(
    ar_events.TYPE_INVOICE_VOIDED,
    ("invoice_number", "customer_id"),
)
register_excerpt_fields(
    ar_events.TYPE_INVOICE_REVERSED,
    (
        "invoice_number",
        "reversing_journal_entry_id",
        "original_journal_entry_id",
    ),
)


# ---------------------------------------------------------------------------
# AR: payments + credit/debit notes + customer credit (Phase 7.4, #112)
# ---------------------------------------------------------------------------
#
# CRITICAL PII RULE: ``reference`` (card last-4, check number,
# marketplace TX id) and ``notes`` MUST NEVER be whitelisted on payment
# events. The whitelist stays narrow: payment_number, customer_id,
# amount, method, journal_entry_id. A regression test in
# ``tests/test_payments_role_matrix.py`` guards the invariant.

register_excerpt_fields(
    ar_events.TYPE_PAYMENT_RECORDED,
    ("payment_number", "customer_id", "amount", "method", "state"),
)
register_excerpt_fields(
    ar_events.TYPE_PAYMENT_APPLIED,
    ("payment_number", "customer_id", "total_applied", "excess_to_credit"),
)
register_excerpt_fields(
    ar_events.TYPE_PAYMENT_POSTED,
    ("payment_number", "customer_id", "amount", "method", "journal_entry_id"),
)
register_excerpt_fields(
    ar_events.TYPE_PAYMENT_UNAPPLIED,
    ("payment_number", "customer_id", "reversing_journal_entry_id"),
)
register_excerpt_fields(
    ar_events.TYPE_PAYMENT_BOUNCED,
    ("payment_number", "customer_id"),
)
register_excerpt_fields(
    ar_events.TYPE_PAYMENT_CANCELLED,
    ("payment_number", "customer_id"),
)

# Credit / debit notes — keep PII out, surface number + ID refs.
register_excerpt_fields(
    ar_events.TYPE_CREDIT_NOTE_CREATED,
    ("credit_note_number", "customer_id", "invoice_id", "reason", "total_amount"),
)
register_excerpt_fields(
    ar_events.TYPE_CREDIT_NOTE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ar_events.TYPE_CREDIT_NOTE_ISSUED,
    ("credit_note_number", "customer_id", "invoice_id", "total_amount", "journal_entry_id"),
)
register_excerpt_fields(
    ar_events.TYPE_CREDIT_NOTE_APPLIED,
    ("credit_note_number", "customer_id", "invoice_id", "amount_applied"),
)
register_excerpt_fields(
    ar_events.TYPE_CREDIT_NOTE_CANCELLED,
    ("credit_note_number", "customer_id", "reversing_journal_entry_id"),
)

register_excerpt_fields(
    ar_events.TYPE_DEBIT_NOTE_CREATED,
    ("debit_note_number", "customer_id", "invoice_id", "reason", "total_amount"),
)
register_excerpt_fields(
    ar_events.TYPE_DEBIT_NOTE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ar_events.TYPE_DEBIT_NOTE_ISSUED,
    ("debit_note_number", "customer_id", "invoice_id", "total_amount", "journal_entry_id"),
)
register_excerpt_fields(
    ar_events.TYPE_DEBIT_NOTE_APPLIED,
    ("debit_note_number", "customer_id", "invoice_id", "amount_applied"),
)
register_excerpt_fields(
    ar_events.TYPE_DEBIT_NOTE_CANCELLED,
    ("debit_note_number", "customer_id", "reversing_journal_entry_id"),
)

# Customer credit — keep notes out.
register_excerpt_fields(
    ar_events.TYPE_CUSTOMER_CREDIT_ACCRUED,
    ("customer_id", "transaction_id", "amount", "source_payment_id", "source_refund_id"),
)
register_excerpt_fields(
    ar_events.TYPE_CUSTOMER_CREDIT_APPLIED,
    ("customer_id", "transaction_id", "amount", "applied_to_invoice_id"),
)


# ---------------------------------------------------------------------------
# AR: recurring invoice templates (Phase 7.5, #113)
# ---------------------------------------------------------------------------
#
# PII RULE: ``notes`` and line-level data (``items``) MUST NEVER be
# whitelisted here. The payload carries them so replay can reconstruct the
# template, but the audit denormalization strictly limits itself to ``name``,
# ``customer_id``, and ``cadence_kind``.

register_excerpt_fields(
    ar_events.TYPE_RECURRING_TEMPLATE_CREATED,
    ("name", "customer_id", "cadence_kind"),
)
register_excerpt_fields(
    ar_events.TYPE_RECURRING_TEMPLATE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ar_events.TYPE_RECURRING_TEMPLATE_PAUSED,
    ("name", "customer_id", "cadence_kind"),
)
register_excerpt_fields(
    ar_events.TYPE_RECURRING_TEMPLATE_RESUMED,
    ("name", "customer_id", "cadence_kind"),
)
register_excerpt_fields(
    ar_events.TYPE_RECURRING_TEMPLATE_CANCELLED,
    ("name", "customer_id", "cadence_kind"),
)
register_excerpt_fields(
    ar_events.TYPE_RECURRING_INVOICE_MATERIALIZED,
    ("name", "customer_id", "cadence_kind", "invoice_id", "invoice_number"),
)


# ---------------------------------------------------------------------------
# AR: late fees + overdue (Phase 7.6, #114)
# ---------------------------------------------------------------------------
#
# PII RULE: ``notes`` on policy create/update MUST NEVER appear here.

register_excerpt_fields(
    ar_events.TYPE_INVOICE_OVERDUE,
    ("invoice_number", "customer_id", "days_overdue", "amount_outstanding"),
)
register_excerpt_fields(
    ar_events.TYPE_LATE_FEE_POLICY_CREATED,
    ("policy_id", "customer_id", "kind", "amount", "apply_after_days"),
)
register_excerpt_fields(
    ar_events.TYPE_LATE_FEE_POLICY_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ar_events.TYPE_LATE_FEE_POLICY_DEACTIVATED,
    ("policy_id", "customer_id"),
)
register_excerpt_fields(
    ar_events.TYPE_LATE_FEE_APPLIED,
    (
        "invoice_number",
        "customer_id",
        "policy_id",
        "debit_note_id",
        "amount",
        "days_overdue",
    ),
)


# ---------------------------------------------------------------------------
# AP: vendors (Phase 8.1, #128)
# ---------------------------------------------------------------------------
#
# CRITICAL PII RULE: ``primary_email``, ``phone``, ``billing_address``,
# ``shipping_address``, ``tax_id``, and ``notes`` MUST NEVER be
# whitelisted here. The payload carries them so replay can reconstruct
# the vendor row, but the audit denormalization keeps strictly to
# ``vendor_number`` + ``display_name``. A regression test in
# ``tests/test_vendor_audit_pii_redacted.py`` guards the invariant.

register_excerpt_fields(
    ap_events.TYPE_VENDOR_CREATED,
    ("vendor_number", "display_name"),
)
register_excerpt_fields(
    ap_events.TYPE_VENDOR_UPDATED,
    ("before", "after"),
)
# Archived / Unarchived carry only the vendor_id — no excerpt is useful.
register_excerpt_fields(
    ap_events.TYPE_VENDOR_CONTACT_ADDED,
    ("contact_id", "role_label", "is_primary"),
)
register_excerpt_fields(
    ap_events.TYPE_VENDOR_CONTACT_UPDATED,
    ("contact_id", "before", "after"),
)
register_excerpt_fields(
    ap_events.TYPE_VENDOR_CONTACT_REMOVED,
    ("contact_id",),
)


# ---------------------------------------------------------------------------
# AP: bills (Phase 8.2, #129)
# ---------------------------------------------------------------------------
#
# PII RULE: ``notes`` and ``billing_address_snapshot`` MUST NEVER be
# whitelisted here. The payload carries them so replay can reconstruct
# the bill, but the audit denormalization keeps strictly to
# ``bill_number``, ``vendor_id``, ``total_amount``, and ``due_at``.

register_excerpt_fields(
    ap_events.TYPE_BILL_CREATED,
    ("bill_number", "vendor_id", "total_amount", "due_at", "vendor_invoice_number"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_ISSUED,
    (
        "bill_number",
        "vendor_id",
        "total_amount",
        "due_at",
        "journal_entry_id",
    ),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_POSTED,
    ("bill_number", "journal_entry_id", "total_amount"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_VOIDED,
    ("bill_number", "vendor_id"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_REVERSED,
    (
        "bill_number",
        "reversing_journal_entry_id",
        "original_journal_entry_id",
    ),
)


# ---------------------------------------------------------------------------
# AP: bill payments (Phase 8.3, #130)
# ---------------------------------------------------------------------------
#
# CRITICAL PII RULE: ``reference_number`` (check #, wire id) and
# ``notes`` MUST NEVER be whitelisted on bill-payment events. The
# whitelist stays narrow: payment_number, vendor_id, amount, method,
# journal_entry_id.

register_excerpt_fields(
    ap_events.TYPE_BILL_PAYMENT_RECORDED,
    ("payment_number", "vendor_id", "amount", "method", "state"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_PAYMENT_APPLIED,
    ("payment_number", "vendor_id", "bill_id", "bill_number", "amount_applied"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_PAYMENT_POSTED,
    ("payment_number", "vendor_id", "amount", "method", "journal_entry_id"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_PAYMENT_UNAPPLIED,
    ("payment_number", "vendor_id", "reversing_journal_entry_id"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_PAYMENT_BOUNCED,
    ("payment_number", "vendor_id"),
)
register_excerpt_fields(
    ap_events.TYPE_BILL_PAYMENT_CANCELLED,
    ("payment_number", "vendor_id"),
)


# ---------------------------------------------------------------------------
# AP: overdue bills (Phase 8.4, #131)
# ---------------------------------------------------------------------------

register_excerpt_fields(
    ap_events.TYPE_BILL_OVERDUE,
    ("bill_number", "vendor_id", "days_overdue", "amount_outstanding"),
)


# ---------------------------------------------------------------------------
# AP: recurring bill templates (Phase 8.5, #132)
# ---------------------------------------------------------------------------
#
# PII RULE: ``notes`` and line-level data (``items``) MUST NEVER be
# whitelisted here. The payload carries them so replay can reconstruct the
# template, but the audit denormalization strictly limits itself to ``name``,
# ``vendor_id``, and ``cadence_kind``.

register_excerpt_fields(
    ap_events.TYPE_RECURRING_BILL_TEMPLATE_CREATED,
    ("name", "vendor_id", "cadence_kind"),
)
register_excerpt_fields(
    ap_events.TYPE_RECURRING_BILL_TEMPLATE_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ap_events.TYPE_RECURRING_BILL_TEMPLATE_PAUSED,
    ("name", "vendor_id", "cadence_kind"),
)
register_excerpt_fields(
    ap_events.TYPE_RECURRING_BILL_TEMPLATE_RESUMED,
    ("name", "vendor_id", "cadence_kind"),
)
register_excerpt_fields(
    ap_events.TYPE_RECURRING_BILL_TEMPLATE_CANCELLED,
    ("name", "vendor_id", "cadence_kind"),
)
register_excerpt_fields(
    ap_events.TYPE_RECURRING_BILL_MATERIALIZED,
    ("name", "vendor_id", "cadence_kind", "bill_id", "bill_number"),
)


# ---------------------------------------------------------------------------
# AP: expense categories (Phase 8.6, #133)
# ---------------------------------------------------------------------------
#
# PII RULE: ``notes`` MUST NEVER be whitelisted. The payload carries it
# so replay can reconstruct the row, but the audit denormalization is
# strictly limited to ``code`` + ``name``.

register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CATEGORY_CREATED,
    ("code", "name"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CATEGORY_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CATEGORY_ARCHIVED,
    ("code", "name"),
)


# ---------------------------------------------------------------------------
# AP: expense claims (Phase 8.7, #134)
# ---------------------------------------------------------------------------
#
# PII RULE: line ``description``, claim ``notes``, and ``rejection_reason``
# MUST NEVER be whitelisted. Payloads carry them for replay, but the audit
# denormalization is strictly limited to claim_number, submitter_user_id,
# state, total_amount, and related IDs.

register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CLAIM_CREATED,
    ("claim_number", "submitter_user_id", "state", "total_amount"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CLAIM_UPDATED,
    ("before", "after"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CLAIM_SUBMITTED,
    ("claim_number", "submitter_user_id", "total_amount", "approval_request_id"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CLAIM_APPROVED,
    ("claim_number", "submitter_user_id", "approver_user_id", "total_amount"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CLAIM_REJECTED,
    ("claim_number", "submitter_user_id", "approver_user_id"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CLAIM_REIMBURSED,
    ("claim_number", "submitter_user_id", "bill_payment_id"),
)
register_excerpt_fields(
    ap_events.TYPE_EXPENSE_CLAIM_CANCELLED,
    ("claim_number", "submitter_user_id"),
)


# ---------------------------------------------------------------------------
# AP: billable expenses (Phase 8.8, #135)
# ---------------------------------------------------------------------------
#
# The link payload is small and contains no PII — just IDs and decimal
# amounts. All fields are safe to surface.

register_excerpt_fields(
    ap_events.TYPE_BILLABLE_EXPENSE_LINKED,
    (
        "source_kind",
        "source_id",
        "invoice_id",
        "invoice_item_id",
        "amount",
        "markup_percent",
    ),
)


# ---------------------------------------------------------------------------
# Banking: bank imports (Phase 8.9, #136)
# ---------------------------------------------------------------------------
#
# PII RULE: ``column_map`` carries operator-named column headers (which
# may include free text) and ``notes`` is a free-form operator field —
# both stay out of audit excerpts. ``description`` / ``memo`` on
# bank_transaction events are not whitelisted either; we only emit
# run-level summary events here, never per-row.

register_excerpt_fields(
    banking_events.TYPE_MAPPING_CREATED,
    ("mapping_id", "account_id", "name", "file_kind", "amount_sign"),
)
register_excerpt_fields(
    banking_events.TYPE_MAPPING_UPDATED,
    ("mapping_id",),
)
register_excerpt_fields(
    banking_events.TYPE_MAPPING_DEACTIVATED,
    ("mapping_id", "account_id", "name"),
)
register_excerpt_fields(
    banking_events.TYPE_IMPORT_RUN_STARTED,
    ("run_id", "account_id", "mapping_id", "filename", "file_kind"),
)
register_excerpt_fields(
    banking_events.TYPE_IMPORT_RUN_COMPLETED,
    (
        "run_id",
        "account_id",
        "mapping_id",
        "filename",
        "row_count",
        "inserted_count",
        "duplicate_count",
        "error_count",
    ),
)
register_excerpt_fields(
    banking_events.TYPE_IMPORT_RUN_FAILED,
    ("run_id", "account_id", "filename", "reason"),
)

# ---------------------------------------------------------------------------
# Banking: match rules + transaction match state (Phase 8.10, #137)
# ---------------------------------------------------------------------------
#
# PII RULE: ``match_value`` is operator-defined and may include free text,
# but is not customer PII; it's a matcher pattern. We surface it for the
# audit trail because the audit excerpt is the only way an operator can
# later answer "what rule did this row hit?". ``notes`` and bank
# ``description`` / ``memo`` stay out.

register_excerpt_fields(
    banking_events.TYPE_MATCH_RULE_CREATED,
    (
        "rule_id",
        "account_id",
        "match_kind",
        "match_field",
        "match_value",
        "action_kind",
        "priority",
    ),
)
register_excerpt_fields(
    banking_events.TYPE_MATCH_RULE_UPDATED,
    ("rule_id",),
)
register_excerpt_fields(
    banking_events.TYPE_MATCH_RULE_DEACTIVATED,
    ("rule_id",),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_TRANSACTION_AUTO_MATCHED,
    ("transaction_id", "rule_id", "journal_entry_id", "amount"),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_TRANSACTION_MANUALLY_MATCHED,
    ("transaction_id", "journal_entry_id", "journal_line_id"),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_TRANSACTION_UNMATCHED,
    ("transaction_id", "previous_journal_line_id"),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_TRANSACTION_IGNORED,
    ("transaction_id", "rule_id"),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_TRANSACTION_FLAGGED_FOR_REVIEW,
    ("transaction_id", "rule_id"),
)

# ---------------------------------------------------------------------------
# Banking: reconciliation + inter-account transfers (Phase 8.11, #138)
# ---------------------------------------------------------------------------
#
# Reconciliation payloads carry only accounting plumbing (account IDs,
# balances, dates) — no PII. ``notes`` stays out, mirroring the rest of
# the banking context.

register_excerpt_fields(
    banking_events.TYPE_BANK_RECONCILIATION_OPENED,
    (
        "recon_id",
        "account_id",
        "period_start",
        "period_end",
        "statement_ending_balance",
    ),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_RECONCILIATION_ITEM_CLEARED,
    ("recon_id", "item_id", "transaction_id"),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_RECONCILIATION_ITEM_UNCLEARED,
    ("recon_id", "item_id", "transaction_id"),
)
register_excerpt_fields(
    banking_events.TYPE_BANK_RECONCILIATION_FINALIZED,
    (
        "recon_id",
        "account_id",
        "period_end",
        "book_ending_balance",
        "statement_ending_balance",
        "difference",
    ),
)
register_excerpt_fields(
    banking_events.TYPE_INTER_ACCOUNT_TRANSFER_POSTED,
    (
        "journal_entry_id",
        "from_account_id",
        "to_account_id",
        "amount",
        "occurred_at",
    ),
)
