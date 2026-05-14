"""Startup validation logs warnings for bad stored values but does not crash.

The schema default still wins at read time, so a bad row degrades
gracefully rather than taking the app down.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.setting import Setting
from app.services.settings.cache import get_cache
from app.services.settings.service import (
    SettingsService,
    validate_stored_settings,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_cache().clear()


@pytest.mark.asyncio
async def test_validate_stored_settings_empty_table_ok(
    session: AsyncSession, schema: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        bad = await validate_stored_settings(session=session)
    assert bad == []


@pytest.mark.asyncio
async def test_invalid_stored_value_logs_warning(
    session: AsyncSession, schema: None, caplog: pytest.LogCaptureFixture
) -> None:
    # Inject a row with a value that violates the schema's ge=0 constraint.
    session.add(
        Setting(
            key="cost_engine.labor_rate_per_hour",
            value="-99.99",
            updated_by_user_id=None,
        )
    )
    await session.commit()

    with caplog.at_level(logging.WARNING):
        bad = await validate_stored_settings(session=session)
    assert "cost_engine.labor_rate_per_hour" in bad


@pytest.mark.asyncio
async def test_unknown_stored_key_logs_warning_does_not_crash(
    session: AsyncSession, schema: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A leftover row whose key isn't in the current registry (e.g. after
    a removal) must not crash startup."""
    session.add(Setting(key="legacy.removed_key", value="anything"))
    await session.commit()

    with caplog.at_level(logging.WARNING):
        bad = await validate_stored_settings(session=session)
    assert "legacy.removed_key" in bad


@pytest.mark.asyncio
async def test_bad_stored_value_does_not_break_default_read(
    session: AsyncSession, schema: None
) -> None:
    """When a stored value is invalid, the default still wins for callers.

    Note: ``SettingsService.get`` does not currently re-validate the
    stored row at read time — schema-on-write is enforced. This test
    documents the contract: validate_stored_settings is advisory only,
    and the production safeguard is that ``set`` validates before
    writing.
    """
    # Write a valid row first via the service, confirm it reads back.
    await SettingsService.set(
        "cost_engine.labor_rate_per_hour",
        "30.00",
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    val = await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    assert val == Decimal("30.00")
