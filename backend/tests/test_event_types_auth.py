"""Auth event-type payload validation."""

from __future__ import annotations

import uuid

import pytest
from app.events.registry import InvalidEventPayloadError, validate_payload
from app.events.types import auth as auth_events


def test_login_succeeded_accepts_good_payload() -> None:
    user_id = uuid.uuid4()
    normalized = validate_payload(
        auth_events.TYPE_LOGIN_SUCCEEDED,
        {"email": "owner@example.com", "user_id": str(user_id)},
    )
    assert normalized["email"] == "owner@example.com"
    assert normalized["user_id"] == str(user_id)


def test_login_failed_rejects_unknown_reason() -> None:
    with pytest.raises(InvalidEventPayloadError):
        validate_payload(
            auth_events.TYPE_LOGIN_FAILED,
            {"email": "x@y", "reason": "exploded"},
        )


def test_login_failed_accepts_known_reasons() -> None:
    for reason in ("unknown_user", "bad_password"):
        validate_payload(
            auth_events.TYPE_LOGIN_FAILED,
            {"email": "x@y", "reason": reason},
        )


def test_rate_limited_endpoint_literal() -> None:
    validate_payload(auth_events.TYPE_RATE_LIMITED, {"endpoint": "login"})
    with pytest.raises(InvalidEventPayloadError):
        validate_payload(auth_events.TYPE_RATE_LIMITED, {"endpoint": "logout"})


def test_logged_out_user_id_optional() -> None:
    validate_payload(auth_events.TYPE_LOGGED_OUT, {})
    validate_payload(auth_events.TYPE_LOGGED_OUT, {"user_id": str(uuid.uuid4())})
