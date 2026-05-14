"""Projection handlers and registry (Phase 1.2).

Projections derive read-model state from the event log. They run
synchronously inside the same DB transaction as the event append, which is
what gives us strict consistency between the event log and its derived
views.

Importing the package side-effects each handler module into the registry
(mirroring ``app.events.types``).
"""

from app.projections import (
    settings_cache,  # noqa: F401
    test_event_projection,  # noqa: F401
)
