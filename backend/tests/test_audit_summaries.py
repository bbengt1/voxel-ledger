"""Audit summary formatter registry."""

from __future__ import annotations

import uuid

from app.events.types import auth as auth_events
from app.projections.audit.summaries import render_summary


def test_login_succeeded_summary() -> None:
    s = render_summary(
        auth_events.TYPE_LOGIN_SUCCEEDED,
        {"email": "owner@example.com", "user_id": str(uuid.uuid4())},
        actor_label="owner@example.com",
        aggregate_type="user",
        aggregate_id="abc",
    )
    assert s == "login succeeded for owner@example.com"


def test_login_failed_summary_includes_reason() -> None:
    s = render_summary(
        auth_events.TYPE_LOGIN_FAILED,
        {"email": "ghost@nope.com", "reason": "unknown_user"},
        actor_label="unknown",
        aggregate_type="user",
        aggregate_id="0",
    )
    assert "ghost@nope.com" in s
    assert "unknown_user" in s


def test_unknown_event_type_falls_through_to_generic() -> None:
    s = render_summary(
        "some.UnregisteredEvent",
        {"foo": "bar"},
        actor_label="alice@x",
        aggregate_type="widget",
        aggregate_id="42",
    )
    assert s == "alice@x did some.UnregisteredEvent on widget:42"
