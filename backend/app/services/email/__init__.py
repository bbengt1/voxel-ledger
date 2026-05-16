"""Email delivery package (Phase 7.7, #115)."""

from app.services.email.service import (
    EmailMessageNotFoundError,
    EmailServiceError,
    InvalidEmailStateError,
    attempt_send,
    backoff_seconds,
    cancel,
    enqueue_email,
    max_attempts,
    run_worker_once,
)

__all__ = [
    "EmailMessageNotFoundError",
    "EmailServiceError",
    "InvalidEmailStateError",
    "attempt_send",
    "backoff_seconds",
    "cancel",
    "enqueue_email",
    "max_attempts",
    "run_worker_once",
]
