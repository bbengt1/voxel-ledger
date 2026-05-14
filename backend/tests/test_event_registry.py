"""Event-type registry: registration, lookup, validation."""

from __future__ import annotations

import pytest
from app.events import registry
from app.events.types._test_event import TestEventPayload
from pydantic import BaseModel


def test_test_event_is_registered_on_import() -> None:
    assert registry.is_registered("test.TestEvent")
    assert registry.get_payload_model("test.TestEvent") is TestEventPayload


def test_register_event_idempotent_for_same_model() -> None:
    # Re-registering the exact (type, model) pair must be a no-op.
    registry.register_event("test.TestEvent", TestEventPayload)


def test_register_event_rejects_conflicting_model() -> None:
    class Other(BaseModel):
        value: int

    with pytest.raises(registry.EventRegistryError):
        registry.register_event("test.TestEvent", Other)


def test_register_event_accepts_new_type() -> None:
    class Payload(BaseModel):
        x: int

    registry.register_event("test.NewlyRegistered", Payload)
    try:
        assert registry.is_registered("test.NewlyRegistered")
    finally:
        registry._REGISTRY.pop("test.NewlyRegistered", None)


def test_validate_payload_returns_json_dict() -> None:
    result = registry.validate_payload("test.TestEvent", {"value": "hi"})
    assert result == {"value": "hi"}


def test_validate_payload_rejects_unknown_type() -> None:
    with pytest.raises(registry.UnknownEventTypeError):
        registry.validate_payload("not.A.Real.Event", {"value": "hi"})


def test_validate_payload_rejects_bad_shape() -> None:
    with pytest.raises(registry.InvalidEventPayloadError):
        registry.validate_payload("test.TestEvent", {"wrong_field": 1})


def test_registered_types_is_sorted() -> None:
    types = registry.registered_types()
    assert types == sorted(types)
    assert "test.TestEvent" in types
