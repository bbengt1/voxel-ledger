"""Audit hook stub for auth events.

Phase 0.7: emit structured log lines so we can grep/route them today.
Phase 1: the same call site will also append to the domain event log.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger

_log = get_logger("audit")


def log_auth_event(
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    ip: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a structured audit log line for an auth event.

    Fields are deliberately flat so Phase 1's event-log persister can
    consume them without a schema upcast. Never log raw tokens or
    passwords from the caller — pass an event_type only.
    """
    payload: dict[str, Any] = {
        "audit": True,
        "event_type": event_type,
        "user_id": str(user_id) if user_id else None,
        "ip": ip,
    }
    if extra:
        payload.update(extra)
    _log.info("auth.event", **payload)
