"""Domain event log package.

Importing this package registers every declared event type — keep that
in mind when adding new bounded-context event modules: import them from
``app.events.types`` so they participate in the registry on app boot.
"""

from app.events import types as _types  # noqa: F401  (side-effect: registration)
from app.events.registry import (
    EventRegistryError,
    InvalidEventPayloadError,
    UnknownEventTypeError,
    get_payload_model,
    is_registered,
    register_event,
    registered_types,
    validate_payload,
)

__all__ = [
    "EventRegistryError",
    "InvalidEventPayloadError",
    "UnknownEventTypeError",
    "get_payload_model",
    "is_registered",
    "register_event",
    "registered_types",
    "validate_payload",
]
