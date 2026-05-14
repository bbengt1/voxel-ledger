"""In-process TTL cache for operational settings.

The settings table is read on most cost-calc / POS / reference allocator
calls. Hitting the DB every time would be wasteful — the table is tiny,
low-cardinality, and changes rarely. We cache (value, fetched_at) per key
with a 5-second TTL and invalidate on the ``settings.SettingChanged``
event via the cache-busting projection.

Single-process, single-tenant deployment, so an in-memory dict is enough.
If the app ever runs multi-worker, we'll need a pub/sub layer here — file
a ticket then; don't over-build now.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_TTL_SECONDS: float = 5.0

_MISS = object()  # Sentinel for "no row in DB" (distinct from None values).


@dataclass
class _Entry:
    value: Any
    fetched_at: float


class SettingsCache:
    """Thread-safe in-process TTL cache. One instance per app."""

    def __init__(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        # Test hooks: counts are nice to have when verifying that a hit
        # really avoided a DB roundtrip.
        self.hits: int = 0
        self.misses: int = 0

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    def get(self, key: str) -> Any | None:
        """Return the cached value for ``key`` if fresh, else ``None``.

        ``None`` is used as the "not cached / expired" signal even though
        ``None`` is itself a legitimate setting value: keys whose value is
        ``None`` are stored under the ``_MISS`` sentinel internally and
        translated back to ``None`` on the way out.
        """
        with self._lock:
            entry = self._store.get(key)
            now = time.monotonic()
            if entry is None or (now - entry.fetched_at) > self._ttl:
                self.misses += 1
                # Eagerly drop the stale row so the dict doesn't grow
                # without bound when callers iterate many keys once.
                if entry is not None:
                    self._store.pop(key, None)
                return None
            self.hits += 1
            return None if entry.value is _MISS else entry.value

    def set(self, key: str, value: Any) -> None:
        """Cache ``value`` for ``key`` with a fresh timestamp."""
        stored = _MISS if value is None else value
        with self._lock:
            self._store[key] = _Entry(value=stored, fetched_at=time.monotonic())

    def invalidate(self, key: str) -> None:
        """Drop a single key (called by the projection on SettingChanged)."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Drop everything. Useful for tests and bulk imports."""
        with self._lock:
            self._store.clear()

    def reset_counters(self) -> None:
        with self._lock:
            self.hits = 0
            self.misses = 0


# Module-level singleton. The projection imports this same object so a
# cache-bust event lands on the cache the service is reading from.
_cache = SettingsCache()


def get_cache() -> SettingsCache:
    return _cache
