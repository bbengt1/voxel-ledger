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
