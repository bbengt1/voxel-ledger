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
from app.events.types import inventory as inventory_events
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
