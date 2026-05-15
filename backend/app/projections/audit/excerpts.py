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
from app.events.types import approvals as approvals_events
from app.events.types import auth as auth_events
from app.events.types import catalog as catalog_events
from app.events.types import custom_fields as cf_events
from app.events.types import inventory as inventory_events
from app.events.types import notes_attachments as notes_events
from app.events.types import production as production_events
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
