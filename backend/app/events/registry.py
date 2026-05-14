"""Event-type registry.

Every event type that may legitimately appear in the event log declares
itself here with a Pydantic payload model. ``EventStore.append`` looks up
the type and validates the payload before persisting; unknown types are
rejected at the boundary so we never store junk we cannot replay.

TODO(phase-1.2): payload upcasters keyed by ``(type, schema_version)``.
TODO(phase-1.2): snapshot strategy per aggregate type.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

_REGISTRY: dict[str, type[BaseModel]] = {}


class EventRegistryError(Exception):
    """Base class for registry-related errors."""


class UnknownEventTypeError(EventRegistryError):
    """An event type was not registered before append."""


class InvalidEventPayloadError(EventRegistryError):
    """The payload failed validation against the registered model."""


def register_event(type_string: str, payload_model: type[BaseModel]) -> None:
    """Register an event type and its payload model.

    Re-registering the same ``(type, model)`` pair is a no-op so module
    imports during test re-imports stay idempotent. Re-registering a
    different model under the same type string raises — that almost
    always indicates a typo or a copy-paste bug.
    """
    existing = _REGISTRY.get(type_string)
    if existing is payload_model:
        return
    if existing is not None:
        raise EventRegistryError(
            f"event type {type_string!r} already registered with a different model"
        )
    _REGISTRY[type_string] = payload_model


def get_payload_model(type_string: str) -> type[BaseModel]:
    try:
        return _REGISTRY[type_string]
    except KeyError as exc:
        raise UnknownEventTypeError(f"event type {type_string!r} is not registered") from exc


def is_registered(type_string: str) -> bool:
    return type_string in _REGISTRY


def validate_payload(type_string: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate ``payload`` against the registered model and return a
    JSON-serializable dict (mode='json'). Used by ``EventStore.append``."""
    model = get_payload_model(type_string)
    try:
        validated = model.model_validate(payload)
    except ValidationError as exc:
        raise InvalidEventPayloadError(
            f"payload for event type {type_string!r} failed validation: {exc}"
        ) from exc
    return validated.model_dump(mode="json")


def registered_types() -> list[str]:
    """Returns the currently registered type strings (sorted, stable)."""
    return sorted(_REGISTRY)
