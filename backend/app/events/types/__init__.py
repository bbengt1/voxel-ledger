"""Concrete event-type payload models. Importing the package side-effects
each type into the registry."""

from app.events.types import (
    _test_event,  # noqa: F401
    accounting,  # noqa: F401
    ap,  # noqa: F401
    approvals,  # noqa: F401
    ar,  # noqa: F401
    auth,  # noqa: F401
    banking,  # noqa: F401
    catalog,  # noqa: F401
    custom_fields,  # noqa: F401
    inventory,  # noqa: F401
    notes_attachments,  # noqa: F401
    production,  # noqa: F401
    sales,  # noqa: F401
    settings,  # noqa: F401
    users,  # noqa: F401
)
