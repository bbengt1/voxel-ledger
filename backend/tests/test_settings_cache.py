"""SettingsCache behavior — hit avoids DB, TTL expires, projection invalidates."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.services.settings import cache as cache_module
from app.services.settings.cache import SettingsCache, get_cache
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_cache().clear()
    get_cache().reset_counters()


def test_cache_hit_within_ttl() -> None:
    c = SettingsCache(ttl_seconds=5.0)
    c.set("k", Decimal("1"))
    assert c.get("k") == Decimal("1")
    assert c.hits == 1
    assert c.misses == 0


def test_cache_expiry_after_ttl() -> None:
    c = SettingsCache(ttl_seconds=0.01)
    c.set("k", "v")
    time.sleep(0.05)
    assert c.get("k") is None  # expired
    assert c.misses == 1


def test_invalidate_drops_entry() -> None:
    c = SettingsCache(ttl_seconds=60.0)
    c.set("k", "v")
    c.invalidate("k")
    assert c.get("k") is None


@pytest.mark.asyncio
async def test_event_driven_invalidation_via_projection(
    session: AsyncSession, schema: None
) -> None:
    """A SettingChanged event must bust the cache through the projection.

    First read warms the cache with the default. Set a new value; the
    projection runs synchronously and invalidates. The next read sees
    the new value within the same logical tick.
    """
    cache = get_cache()
    # Warm the cache with the default.
    v1 = await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    assert v1 == Decimal("25.00")
    assert "cost_engine.labor_rate_per_hour" in cache._store  # populated

    # Change the value — the projection should bust the cache entry.
    await SettingsService.set(
        "cost_engine.labor_rate_per_hour",
        "77.77",
        session=session,
        actor_user_id=None,
    )
    await session.commit()

    # After the set, the next read returns the new value.
    v2 = await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    assert v2 == Decimal("77.77")


@pytest.mark.asyncio
async def test_repeated_read_uses_cache(session: AsyncSession, schema: None) -> None:
    cache = get_cache()
    cache.reset_counters()
    # First read: miss (no DB row, returns default; cache populated).
    await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    miss_count_after_first = cache.misses
    hit_count_after_first = cache.hits

    # Second read: hit.
    await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    assert cache.hits == hit_count_after_first + 1
    assert cache.misses == miss_count_after_first


def test_default_ttl_is_five_seconds() -> None:
    assert cache_module.DEFAULT_TTL_SECONDS == 5.0
    assert get_cache().ttl_seconds == 5.0
