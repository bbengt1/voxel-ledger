"""Per-event-type summary formatters for the audit log.

A summary is a short human-readable one-liner stored on the audit_log row
so the query API can render the index without re-deserializing payloads.
Each event type registers its own formatter; unknown types fall through
to a generic "{actor} did {event_type} on {aggregate_type}:{aggregate_id}".

Formatters MUST be pure functions of ``(payload, actor_label)`` — no DB,
no clock. The actor label is whatever the projection resolved (the user's
email if known, otherwise ``"unknown"``).
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
from app.events.types import users as users_events

Formatter = Callable[[dict[str, Any], str], str]

_REGISTRY: dict[str, Formatter] = {}


def register_summary(event_type: str, fn: Formatter) -> None:
    """Register a summary formatter for an event type.

    Re-registering the same callable is idempotent (so test module reloads
    don't trip). Re-registering a different callable raises.
    """
    existing = _REGISTRY.get(event_type)
    if existing is fn:
        return
    if existing is not None:
        raise ValueError(
            f"summary formatter for {event_type!r} already registered with a different callable"
        )
    _REGISTRY[event_type] = fn


def render_summary(
    event_type: str,
    payload: dict[str, Any],
    *,
    actor_label: str,
    aggregate_type: str,
    aggregate_id: str,
) -> str:
    """Render the summary string for one event. Falls through to the
    generic format for unregistered event types."""
    fn = _REGISTRY.get(event_type)
    if fn is None:
        return f"{actor_label} did {event_type} on {aggregate_type}:{aggregate_id}"
    return fn(payload, actor_label)


# ---------------------------------------------------------------------------
# Auth-event summaries
# ---------------------------------------------------------------------------


def _login_succeeded(payload: dict[str, Any], _actor: str) -> str:
    return f"login succeeded for {payload.get('email', '?')}"


def _login_failed(payload: dict[str, Any], _actor: str) -> str:
    return f"login failed for {payload.get('email', '?')} ({payload.get('reason', '?')})"


def _login_inactive(payload: dict[str, Any], _actor: str) -> str:
    return f"login rejected (inactive) for {payload.get('email', '?')}"


def _refresh_rotated(_payload: dict[str, Any], actor: str) -> str:
    return f"{actor} rotated refresh token"


def _family_revoked(payload: dict[str, Any], actor: str) -> str:
    reason = payload.get("reason", "?")
    return f"refresh family revoked for {actor} ({reason})"


def _logged_out(_payload: dict[str, Any], actor: str) -> str:
    return f"{actor} logged out"


def _rate_limited(payload: dict[str, Any], _actor: str) -> str:
    return f"rate-limited on {payload.get('endpoint', '?')}"


register_summary(auth_events.TYPE_LOGIN_SUCCEEDED, _login_succeeded)
register_summary(auth_events.TYPE_LOGIN_FAILED, _login_failed)
register_summary(auth_events.TYPE_LOGIN_INACTIVE, _login_inactive)
register_summary(auth_events.TYPE_REFRESH_ROTATED, _refresh_rotated)
register_summary(auth_events.TYPE_FAMILY_REVOKED, _family_revoked)
register_summary(auth_events.TYPE_LOGGED_OUT, _logged_out)
register_summary(auth_events.TYPE_RATE_LIMITED, _rate_limited)


# ---------------------------------------------------------------------------
# Users-admin event summaries (Phase 1.6)
# ---------------------------------------------------------------------------


def _user_created(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} created user {payload.get('email', '?')} as {payload.get('role', '?')}"


def _user_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated user {payload.get('user_id', '?')}: {changes}"


def _user_deactivated(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} deactivated user {payload.get('user_id', '?')} "
        f"({payload.get('reason', 'admin_action')})"
    )


def _user_reactivated(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} reactivated user {payload.get('user_id', '?')}"


def _password_reset_by_admin(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} reset password for user {payload.get('user_id', '?')}"


register_summary(users_events.TYPE_USER_CREATED, _user_created)
register_summary(users_events.TYPE_USER_UPDATED, _user_updated)
register_summary(users_events.TYPE_USER_DEACTIVATED, _user_deactivated)
register_summary(users_events.TYPE_USER_REACTIVATED, _user_reactivated)
register_summary(users_events.TYPE_PASSWORD_RESET_BY_ADMIN, _password_reset_by_admin)


# ---------------------------------------------------------------------------
# Catalog event summaries (Phase 2.1)
# ---------------------------------------------------------------------------


def _material_created(payload: dict[str, Any], actor: str) -> str:
    bits = [payload.get("name", "?")]
    brand = payload.get("brand")
    if brand:
        bits.append(f"({brand})")
    mt = payload.get("material_type")
    if mt:
        bits.append(f"[{mt}]")
    return f"{actor} created material {' '.join(bits)}"


def _material_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated material {payload.get('material_id', '?')}: {changes}"


def _material_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived material {payload.get('material_id', '?')}"


def _material_unarchived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unarchived material {payload.get('material_id', '?')}"


register_summary(catalog_events.TYPE_MATERIAL_CREATED, _material_created)
register_summary(catalog_events.TYPE_MATERIAL_UPDATED, _material_updated)
register_summary(catalog_events.TYPE_MATERIAL_ARCHIVED, _material_archived)
register_summary(catalog_events.TYPE_MATERIAL_UNARCHIVED, _material_unarchived)


# --- Products (Phase 2.3) -------------------------------------------------


def _product_created(payload: dict[str, Any], actor: str) -> str:
    sku = payload.get("sku", "?")
    name = payload.get("name", "?")
    category = payload.get("category")
    suffix = f" [{category}]" if category else ""
    return f"{actor} created product {sku} ({name}){suffix}"


def _product_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated product {payload.get('product_id', '?')}: {changes}"


def _product_price_changed(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} changed product {payload.get('product_id', '?')} price "
        f"{payload.get('old_price', '?')} -> {payload.get('new_price', '?')}"
    )


def _product_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived product {payload.get('product_id', '?')}"


def _product_unarchived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unarchived product {payload.get('product_id', '?')}"


register_summary(catalog_events.TYPE_PRODUCT_CREATED, _product_created)
register_summary(catalog_events.TYPE_PRODUCT_UPDATED, _product_updated)
register_summary(catalog_events.TYPE_PRODUCT_PRICE_CHANGED, _product_price_changed)
register_summary(catalog_events.TYPE_PRODUCT_ARCHIVED, _product_archived)
register_summary(catalog_events.TYPE_PRODUCT_UNARCHIVED, _product_unarchived)


# --- BOM (Phase 2.4) ----------------------------------------------------


def _bom_component_added(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} added {payload.get('component_kind', '?')}:"
        f"{payload.get('component_id', '?')} x{payload.get('quantity', '?')} "
        f"to product {payload.get('parent_product_id', '?')}"
    )


def _bom_component_removed(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} removed {payload.get('component_kind', '?')}:"
        f"{payload.get('component_id', '?')} from product "
        f"{payload.get('parent_product_id', '?')}"
    )


def _bom_component_quantity_changed(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} changed BOM item {payload.get('bom_item_id', '?')} qty "
        f"{payload.get('old_quantity', '?')} -> {payload.get('new_quantity', '?')}"
    )


def _product_cost_changed(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} rolled product {payload.get('product_id', '?')} cost "
        f"{payload.get('old_cost', '?')} -> {payload.get('new_cost', '?')}"
    )


register_summary(catalog_events.TYPE_BOM_COMPONENT_ADDED, _bom_component_added)
register_summary(catalog_events.TYPE_BOM_COMPONENT_REMOVED, _bom_component_removed)
register_summary(
    catalog_events.TYPE_BOM_COMPONENT_QUANTITY_CHANGED,
    _bom_component_quantity_changed,
)
register_summary(catalog_events.TYPE_PRODUCT_COST_CHANGED, _product_cost_changed)


# ---------------------------------------------------------------------------
# Inventory event summaries (Phase 2.1)
# ---------------------------------------------------------------------------


def _material_received(payload: dict[str, Any], actor: str) -> str:
    grams = payload.get("grams", "?")
    total = payload.get("total_cost", "?")
    mid = payload.get("material_id", "?")
    return f"{actor} received {grams}g for material {mid} (total {total})"


register_summary(inventory_events.TYPE_MATERIAL_RECEIVED, _material_received)


# --- Inventory locations (Phase 3.1) ---


def _location_created(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} created inventory location {payload.get('code', '?')} "
        f"({payload.get('name', '?')}) [{payload.get('kind', '?')}]"
    )


def _location_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated inventory location {payload.get('location_id', '?')}: {changes}"


def _location_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived inventory location {payload.get('location_id', '?')}"


def _location_unarchived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unarchived inventory location {payload.get('location_id', '?')}"


register_summary(inventory_events.TYPE_LOCATION_CREATED, _location_created)
register_summary(inventory_events.TYPE_LOCATION_UPDATED, _location_updated)
register_summary(inventory_events.TYPE_LOCATION_ARCHIVED, _location_archived)
register_summary(inventory_events.TYPE_LOCATION_UNARCHIVED, _location_unarchived)


# --- Inventory transactions (Phase 3.2) ---


def _transaction_recorded(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} recorded {payload.get('kind', '?')} "
        f"{payload.get('signed_quantity', '?')} of "
        f"{payload.get('entity_kind', '?')}:{payload.get('entity_id', '?')} "
        f"@ location {payload.get('location_id', '?')}"
    )


register_summary(inventory_events.TYPE_TRANSACTION_RECORDED, _transaction_recorded)


# ---------------------------------------------------------------------------
# Catalog: Supplies (Phase 2.2)
# ---------------------------------------------------------------------------


def _supply_created(payload: dict[str, Any], actor: str) -> str:
    bits = [payload.get("name", "?")]
    vendor = payload.get("vendor")
    if vendor:
        bits.append(f"({vendor})")
    unit = payload.get("unit")
    cost = payload.get("unit_cost")
    if unit and cost is not None:
        bits.append(f"@ {cost}/{unit}")
    return f"{actor} created supply {' '.join(bits)}"


def _supply_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated supply {payload.get('supply_id', '?')}: {changes}"


def _supply_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived supply {payload.get('supply_id', '?')}"


def _supply_unarchived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unarchived supply {payload.get('supply_id', '?')}"


register_summary(catalog_events.TYPE_SUPPLY_CREATED, _supply_created)
register_summary(catalog_events.TYPE_SUPPLY_UPDATED, _supply_updated)
register_summary(catalog_events.TYPE_SUPPLY_ARCHIVED, _supply_archived)
register_summary(catalog_events.TYPE_SUPPLY_UNARCHIVED, _supply_unarchived)


# ---------------------------------------------------------------------------
# Catalog: Rates (Phase 2.2)
# ---------------------------------------------------------------------------


def _rate_created(payload: dict[str, Any], actor: str) -> str:
    kind = payload.get("kind", "?")
    name = payload.get("name", "?")
    value = payload.get("value", "?")
    default = " (default)" if payload.get("is_default_for_kind") else ""
    return f"{actor} created {kind} rate {name} = {value}{default}"


def _rate_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated rate {payload.get('rate_id', '?')}: {changes}"


def _rate_defaulted(payload: dict[str, Any], actor: str) -> str:
    prev = payload.get("previous_default_rate_id")
    kind = payload.get("kind", "?")
    suffix = f" (previously {prev})" if prev else ""
    return f"{actor} set rate {payload.get('rate_id', '?')} as default for {kind}{suffix}"


def _rate_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived rate {payload.get('rate_id', '?')}"


def _rate_unarchived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unarchived rate {payload.get('rate_id', '?')}"


register_summary(catalog_events.TYPE_RATE_CREATED, _rate_created)
register_summary(catalog_events.TYPE_RATE_UPDATED, _rate_updated)
register_summary(catalog_events.TYPE_RATE_DEFAULTED, _rate_defaulted)
register_summary(catalog_events.TYPE_RATE_ARCHIVED, _rate_archived)
register_summary(catalog_events.TYPE_RATE_UNARCHIVED, _rate_unarchived)


# --- Custom fields / form templates (Phase 2.5) ---


def _cf_created(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} added {payload.get('field_type', '?')} custom field "
        f"{payload.get('key', '?')} on {payload.get('entity_type', '?')}"
    )


def _cf_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated custom field {payload.get('custom_field_id', '?')}: {changes}"


def _cf_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived custom field {payload.get('custom_field_id', '?')}"


def _cf_unarchived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unarchived custom field {payload.get('custom_field_id', '?')}"


def _ft_created(payload: dict[str, Any], actor: str) -> str:
    suffix = " (default)" if payload.get("is_default_for_entity_type") else ""
    return (
        f"{actor} created form template {payload.get('name', '?')!r} "
        f"for {payload.get('entity_type', '?')}{suffix}"
    )


def _ft_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated form template {payload.get('template_id', '?')}: {changes}"


def _ft_defaulted(payload: dict[str, Any], actor: str) -> str:
    prev = payload.get("previous_default_template_id")
    et = payload.get("entity_type", "?")
    suffix = f" (previously {prev})" if prev else ""
    return f"{actor} set template {payload.get('template_id', '?')} as default for {et}{suffix}"


def _ft_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived form template {payload.get('template_id', '?')}"


def _ft_field_added(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} added field {payload.get('custom_field_id', '?')} to "
        f"template {payload.get('template_id', '?')}"
    )


def _ft_field_removed(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} removed field {payload.get('custom_field_id', '?')} from "
        f"template {payload.get('template_id', '?')}"
    )


register_summary(cf_events.TYPE_CUSTOM_FIELD_CREATED, _cf_created)
register_summary(cf_events.TYPE_CUSTOM_FIELD_UPDATED, _cf_updated)
register_summary(cf_events.TYPE_CUSTOM_FIELD_ARCHIVED, _cf_archived)
register_summary(cf_events.TYPE_CUSTOM_FIELD_UNARCHIVED, _cf_unarchived)
register_summary(cf_events.TYPE_FORM_TEMPLATE_CREATED, _ft_created)
register_summary(cf_events.TYPE_FORM_TEMPLATE_UPDATED, _ft_updated)
register_summary(cf_events.TYPE_FORM_TEMPLATE_DEFAULTED, _ft_defaulted)
register_summary(cf_events.TYPE_FORM_TEMPLATE_ARCHIVED, _ft_archived)
register_summary(cf_events.TYPE_FORM_TEMPLATE_FIELD_ADDED, _ft_field_added)
register_summary(cf_events.TYPE_FORM_TEMPLATE_FIELD_REMOVED, _ft_field_removed)


# --- Notes & attachments (Phase 2.6) ---


def _note_created(payload: dict[str, Any], actor: str) -> str:
    preview = payload.get("body_preview", "")
    return (
        f"{actor} added note on {payload.get('entity_kind', '?')}:"
        f"{payload.get('entity_id', '?')}: {preview!r}"
    )


def _note_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("body_preview_before", "")
    after = payload.get("body_preview_after", "")
    return f"{actor} updated note {payload.get('note_id', '?')}: " f"{before!r} -> {after!r}"


def _note_deleted(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} deleted note {payload.get('note_id', '?')} from "
        f"{payload.get('entity_kind', '?')}:{payload.get('entity_id', '?')}"
    )


def _note_pinned(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} pinned note {payload.get('note_id', '?')}"


def _note_unpinned(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unpinned note {payload.get('note_id', '?')}"


def _attachment_uploaded(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} uploaded {payload.get('filename', '?')} "
        f"({payload.get('mime_type', '?')}, {payload.get('byte_size', '?')} bytes) "
        f"to {payload.get('entity_kind', '?')}:{payload.get('entity_id', '?')}"
    )


def _attachment_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived attachment {payload.get('attachment_id', '?')}"


register_summary(notes_events.TYPE_NOTE_CREATED, _note_created)
register_summary(notes_events.TYPE_NOTE_UPDATED, _note_updated)
register_summary(notes_events.TYPE_NOTE_DELETED, _note_deleted)
register_summary(notes_events.TYPE_NOTE_PINNED, _note_pinned)
register_summary(notes_events.TYPE_NOTE_UNPINNED, _note_unpinned)
register_summary(notes_events.TYPE_ATTACHMENT_UPLOADED, _attachment_uploaded)
register_summary(notes_events.TYPE_ATTACHMENT_ARCHIVED, _attachment_archived)


# --- Accounting: accounts (Phase 4.1) ---


def _account_created(payload: dict[str, Any], actor: str) -> str:
    parent = payload.get("parent_account_id")
    suffix = f" (parent {parent})" if parent else ""
    return (
        f"{actor} created account {payload.get('code', '?')} "
        f"({payload.get('name', '?')}) [{payload.get('type', '?')}]{suffix}"
    )


def _account_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated account {payload.get('account_id', '?')}: {changes}"


def _account_archived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} archived account {payload.get('account_id', '?')}"


def _account_unarchived(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} unarchived account {payload.get('account_id', '?')}"


register_summary(accounting_events.TYPE_ACCOUNT_CREATED, _account_created)
register_summary(accounting_events.TYPE_ACCOUNT_UPDATED, _account_updated)
register_summary(accounting_events.TYPE_ACCOUNT_ARCHIVED, _account_archived)
register_summary(accounting_events.TYPE_ACCOUNT_UNARCHIVED, _account_unarchived)


# --- Accounting: journal entries (Phase 4.2) ---


def _journal_entry_posted(payload: dict[str, Any], actor: str) -> str:
    lines = payload.get("lines") or []
    return (
        f"{actor} posted journal entry {payload.get('entry_number', '?')} "
        f"({len(lines)} lines): {payload.get('description', '?')}"
    )


def _journal_entry_reversed(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} reversed journal entry {payload.get('original_entry_id', '?')} "
        f"via {payload.get('reversal_entry_number', '?')}"
    )


register_summary(accounting_events.TYPE_JOURNAL_ENTRY_POSTED, _journal_entry_posted)
register_summary(accounting_events.TYPE_JOURNAL_ENTRY_REVERSED, _journal_entry_reversed)


# --- Accounting: periods (Phase 4.3) ---


def _period_created(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} created accounting period {payload.get('name', '?')} "
        f"({payload.get('start_date', '?')}..{payload.get('end_date', '?')})"
    )


def _period_updated(payload: dict[str, Any], actor: str) -> str:
    before = payload.get("before") or {}
    after = payload.get("after") or {}
    fields = sorted(set(before) | set(after))
    changes = ", ".join(f"{f}: {before.get(f)!r} -> {after.get(f)!r}" for f in fields)
    return f"{actor} updated accounting period {payload.get('period_id', '?')}: {changes}"


def _period_closed(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} closed accounting period {payload.get('period_id', '?')}"


def _period_reopened(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} reopened accounting period {payload.get('period_id', '?')}"


def _period_locked(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} locked accounting period {payload.get('period_id', '?')}"


register_summary(accounting_events.TYPE_PERIOD_CREATED, _period_created)
register_summary(accounting_events.TYPE_PERIOD_UPDATED, _period_updated)
register_summary(accounting_events.TYPE_PERIOD_CLOSED, _period_closed)
register_summary(accounting_events.TYPE_PERIOD_REOPENED, _period_reopened)
register_summary(accounting_events.TYPE_PERIOD_LOCKED, _period_locked)


# --- Approvals (Phase 4.4) ---


def _approval_requested(payload: dict[str, Any], actor: str) -> str:
    return (
        f"{actor} requested approval [{payload.get('request_type', '?')}] "
        f"on {payload.get('subject_kind', '?')}:"
        f"{payload.get('subject_id', '?')}"
    )


def _approval_approved(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} approved request {payload.get('request_id', '?')}"


def _approval_rejected(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} rejected request {payload.get('request_id', '?')}"


def _approval_cancelled(payload: dict[str, Any], actor: str) -> str:
    return f"{actor} cancelled request {payload.get('request_id', '?')}"


register_summary(approvals_events.TYPE_APPROVAL_REQUESTED, _approval_requested)
register_summary(approvals_events.TYPE_APPROVAL_APPROVED, _approval_approved)
register_summary(approvals_events.TYPE_APPROVAL_REJECTED, _approval_rejected)
register_summary(approvals_events.TYPE_APPROVAL_CANCELLED, _approval_cancelled)
