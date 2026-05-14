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

from app.events.types import auth as auth_events
from app.events.types import catalog as catalog_events
from app.events.types import inventory as inventory_events
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


# ---------------------------------------------------------------------------
# Inventory event summaries (Phase 2.1)
# ---------------------------------------------------------------------------


def _material_received(payload: dict[str, Any], actor: str) -> str:
    grams = payload.get("grams", "?")
    total = payload.get("total_cost", "?")
    mid = payload.get("material_id", "?")
    return f"{actor} received {grams}g for material {mid} (total {total})"


register_summary(inventory_events.TYPE_MATERIAL_RECEIVED, _material_received)


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
