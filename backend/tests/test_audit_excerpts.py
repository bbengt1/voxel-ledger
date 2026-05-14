"""Audit payload_excerpt whitelist enforcement."""

from __future__ import annotations

import pytest
from app.events.types import auth as auth_events
from app.projections.audit.excerpts import (
    compute_excerpt,
    register_excerpt_fields,
)


def test_unknown_event_type_has_no_excerpt() -> None:
    assert compute_excerpt("some.Unregistered", {"x": 1}) is None


def test_auth_login_succeeded_only_email() -> None:
    excerpt = compute_excerpt(
        auth_events.TYPE_LOGIN_SUCCEEDED,
        {
            "email": "owner@example.com",
            "user_id": "abc",
            "password": "PLAINTEXT",
            "token_hash": "DEADBEEF",
        },
    )
    assert excerpt == {"email": "owner@example.com"}


def test_password_field_never_in_excerpt_even_if_present() -> None:
    """Belt-and-suspenders: forbidden fields cannot be registered."""
    with pytest.raises(ValueError):
        register_excerpt_fields("evil.Event", ("password",))
    with pytest.raises(ValueError):
        register_excerpt_fields("evil.Event", ("token_hash",))


def test_login_failed_excerpt_has_email_but_no_reason() -> None:
    # reason is not whitelisted — read it from the event row if you need it.
    excerpt = compute_excerpt(
        auth_events.TYPE_LOGIN_FAILED,
        {"email": "x@y", "reason": "bad_password"},
    )
    assert excerpt == {"email": "x@y"}


def test_refresh_rotated_has_no_excerpt() -> None:
    assert compute_excerpt(auth_events.TYPE_REFRESH_ROTATED, {"user_id": "abc"}) is None
