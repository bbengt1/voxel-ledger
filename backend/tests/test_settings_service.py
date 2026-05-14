"""SettingsService get / set / list_all / set_many behavior.

Schema fixtures: in-memory SQLite, schema.create_all from the shared
Base. We exercise the service directly (no HTTP), so the event store and
projection wiring run end-to-end with the cache invalidator firing
in-process.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.event import Event
from app.models.setting import Setting
from app.services.settings.cache import get_cache
from app.services.settings.schemas import UnknownSettingError
from app.services.settings.service import (
    SettingsService,
    SettingValidationError,
    key_to_aggregate_id,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Cache is a process-wide singleton; reset it per test."""
    get_cache().clear()
    get_cache().reset_counters()


@pytest.mark.asyncio
async def test_get_with_no_row_returns_default(session: AsyncSession, schema: None) -> None:
    val = await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    assert val == Decimal("25.00")


@pytest.mark.asyncio
async def test_get_unknown_key_raises(session: AsyncSession, schema: None) -> None:
    with pytest.raises(UnknownSettingError):
        await SettingsService.get("nope.not.real", session=session)


@pytest.mark.asyncio
async def test_set_persists_and_returns_typed_value(session: AsyncSession, schema: None) -> None:
    val = await SettingsService.set(
        "cost_engine.labor_rate_per_hour",
        "42.50",
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    assert val == Decimal("42.50")
    # Row is persisted.
    row = (
        await session.execute(
            select(Setting).where(Setting.key == "cost_engine.labor_rate_per_hour")
        )
    ).scalar_one()
    assert row.value == "42.50"


@pytest.mark.asyncio
async def test_set_emits_setting_changed_event(session: AsyncSession, schema: None) -> None:
    await SettingsService.set(
        "cost_engine.labor_rate_per_hour",
        "30.00",
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    events = (await session.execute(select(Event))).scalars().all()
    setting_events = [e for e in events if e.type == "settings.SettingChanged"]
    assert len(setting_events) == 1
    ev = setting_events[0]
    assert ev.payload["key"] == "cost_engine.labor_rate_per_hour"
    # Old value is the default (since no row existed).
    assert ev.payload["old_value"] == "25.00"
    assert ev.payload["new_value"] == "30.00"
    # Aggregate id is deterministic for the same key.
    assert ev.aggregate_id == key_to_aggregate_id("cost_engine.labor_rate_per_hour")


@pytest.mark.asyncio
async def test_set_then_get_returns_new_value(session: AsyncSession, schema: None) -> None:
    await SettingsService.set(
        "cost_engine.overhead_percent",
        "20",
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    val = await SettingsService.get("cost_engine.overhead_percent", session=session)
    assert val == Decimal("20")


@pytest.mark.asyncio
async def test_set_bad_value_raises_validation_error(session: AsyncSession, schema: None) -> None:
    with pytest.raises(SettingValidationError):
        await SettingsService.set(
            "cost_engine.overhead_percent",
            "9999",  # > 100
            session=session,
            actor_user_id=None,
        )


@pytest.mark.asyncio
async def test_set_many_is_atomic_on_invalid_value(session: AsyncSession, schema: None) -> None:
    """One invalid value rolls everything back."""
    with pytest.raises(SettingValidationError):
        await SettingsService.set_many(
            {
                "cost_engine.labor_rate_per_hour": "50.00",
                "cost_engine.overhead_percent": "9999",  # invalid
            },
            session=session,
            actor_user_id=None,
        )
    # Nothing was written.
    rows = (await session.execute(select(Setting))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_set_many_happy_path(session: AsyncSession, schema: None) -> None:
    out = await SettingsService.set_many(
        {
            "cost_engine.labor_rate_per_hour": "50.00",
            "cost_engine.overhead_percent": "10",
        },
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    assert out["cost_engine.labor_rate_per_hour"] == Decimal("50.00")
    assert out["cost_engine.overhead_percent"] == Decimal("10")


@pytest.mark.asyncio
async def test_list_all_merges_defaults_with_stored(session: AsyncSession, schema: None) -> None:
    await SettingsService.set(
        "cost_engine.labor_rate_per_hour",
        "99.99",
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    records = await SettingsService.list_all(session=session)
    by_key = {r.key: r for r in records}
    # Stored row: stored value + non-null updated_at.
    assert by_key["cost_engine.labor_rate_per_hour"].value == Decimal("99.99")
    assert by_key["cost_engine.labor_rate_per_hour"].updated_at is not None
    # Default-only row: default value + null updated_at.
    assert by_key["pos.barcode_scan_padding"].value == "0"
    assert by_key["pos.barcode_scan_padding"].updated_at is None
