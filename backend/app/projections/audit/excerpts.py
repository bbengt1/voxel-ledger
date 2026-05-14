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

from typing import Any

from app.events.types import auth as auth_events
from app.events.types import catalog as catalog_events
from app.events.types import custom_fields as cf_events
from app.events.types import inventory as inventory_events
from app.events.types import notes_attachments as notes_events
from app.events.types import users as users_events

# Event type → tuple of allowed payload field names. Empty/absent = no
# excerpt at all.
_WHITELIST: dict[str, tuple[str, ...]] = {}

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
        if field in payload:
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
