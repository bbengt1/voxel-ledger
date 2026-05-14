"""Minimal in-memory token bucket keyed by client IP.

Good enough for Phase 0.7 login throttling on a single backend node.
Phase 11 may swap this for a Postgres- or Redis-backed limiter.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class InMemoryRateLimiter:
    """Simple token bucket. `capacity` tokens, refilled at `rate_per_sec`."""

    def __init__(self, capacity: int, rate_per_sec: float) -> None:
        self.capacity = capacity
        self.rate_per_sec = rate_per_sec
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Consume one token for `key`. Returns False if the bucket is dry."""
        ts = now if now is not None else time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity - 1, last_refill=ts)
                self._buckets[key] = bucket
                return True
            elapsed = max(0.0, ts - bucket.last_refill)
            bucket.tokens = min(
                self.capacity, bucket.tokens + elapsed * self.rate_per_sec
            )
            bucket.last_refill = ts
            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True
            return False

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def client_ip(request: object) -> str:
    """Pull the client IP from `X-Forwarded-For` first, else the socket addr.

    Typed as `object` because we want this importable without dragging
    starlette into the public surface, but at runtime we expect a Request.
    """
    headers = getattr(request, "headers", {})
    xff = headers.get("x-forwarded-for") if hasattr(headers, "get") else None
    if xff:
        return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return client.host
    return "unknown"
