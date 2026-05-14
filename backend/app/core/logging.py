"""Structured JSON logging.

Every log line carries `ts`, `level`, `msg`, and `request_id` (when set by
the request-id middleware). Uses structlog over stdlib logging so we get
contextvar propagation for free.
"""

from __future__ import annotations

import contextvars
import logging
import sys

import structlog

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def _inject_request_id(
    _logger: object, _method: str, event_dict: dict[str, object]
) -> dict[str, object]:
    rid = request_id_var.get()
    if rid is not None:
        event_dict["request_id"] = rid
    return event_dict


def _rename_event_to_msg(
    _logger: object, _method: str, event_dict: dict[str, object]
) -> dict[str, object]:
    if "event" in event_dict and "msg" not in event_dict:
        event_dict["msg"] = event_dict.pop("event")
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure stdlib + structlog to emit JSON with required fields."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            _inject_request_id,
            _rename_event_to_msg,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[return-value]
