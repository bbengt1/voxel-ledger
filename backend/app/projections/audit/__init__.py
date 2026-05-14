"""Audit-log projection (Phase 1.4).

Subscribes to every event (``event_type='*'``) and writes one row to the
``audit_log`` read model per event. The summary formatter and the
payload_excerpt whitelist are per-event-type registries; unknown event
types fall through to a generic summary and emit no excerpt (deny by
default).

Importing this package side-effects the handler into the projection
registry, matching the convention from ``app.projections``.
"""

from app.projections.audit import excerpts as _excerpts  # noqa: F401
from app.projections.audit import handler  # noqa: F401
from app.projections.audit import summaries as _summaries  # noqa: F401
