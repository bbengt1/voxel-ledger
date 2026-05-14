"""Projection: cache invalidator for the operational settings store.

Subscribes to ``settings.SettingChanged`` and busts the matching entry in
the in-process ``SettingsCache``. The next read for that key falls through
to the DB and re-warms the cache.

This handler does NOT write to a read-model table — the ``setting`` table
itself is the canonical store, not a derived view. We still register
through the projection registry so the event-driven invalidation hook is
visible alongside every other event subscriber. The
``read_model_tables`` tuple is a sentinel virtual table name so the
rebuild script will refuse to truncate it (the registry currently
requires a non-empty tuple).

Replay safety
-------------
The handler is idempotent — calling ``invalidate`` on a key that isn't in
the cache is a no-op. During a full replay we will invalidate every key
many times; that's fine.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types.settings import TYPE_SETTING_CHANGED
from app.models.event import Event
from app.projections.registry import projection
from app.services.settings.cache import get_cache

HANDLER_NAME = "settings_cache_invalidator"
# Sentinel. There is no real ``setting`` read-model table — the canonical
# ``setting`` table is owned by ``SettingsService``, not by this
# projection. Using an obviously-fake name surfaces any rebuild attempt
# loudly instead of silently truncating real data.
READ_MODEL_TABLES: tuple[str, ...] = ("_settings_cache_virtual",)


@projection(
    event_type=TYPE_SETTING_CHANGED,
    name=HANDLER_NAME,
    read_model_tables=READ_MODEL_TABLES,
)
async def invalidate_settings_cache(event: Event, _session: AsyncSession) -> None:
    """Bust the cache entry for the changed key.

    The payload was validated at append time by the event registry, so
    ``key`` is guaranteed to be a string. We don't touch any DB tables,
    so ``session`` is unused — the parameter is part of the handler
    contract.
    """
    payload = event.payload or {}
    key = payload.get("key")
    if isinstance(key, str) and key:
        get_cache().invalidate(key)
