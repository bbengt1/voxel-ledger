"""Outbound webhook dispatcher (Phase 11.1, #193)."""

from app.services.webhooks.dispatcher import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_BACKOFF_SECONDS,
    SIGNATURE_HEADER,
    DeliverResult,
    backoff_for_attempt,
    deliver,
    enqueue,
    next_backoff,
    replay,
    run_pending,
    sign_payload,
)

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_BACKOFF_SECONDS",
    "SIGNATURE_HEADER",
    "DeliverResult",
    "backoff_for_attempt",
    "deliver",
    "enqueue",
    "next_backoff",
    "replay",
    "run_pending",
    "sign_payload",
]
