"""Decimal precision round-trip.

The point: a stored Decimal must come back as a real Decimal (or its
canonical string representation), not as a float. We store via JSON, and
JSON's only numeric type is the IEEE float — so the service has to
encode/decode Decimals as strings.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.setting import Setting
from app.services.settings.cache import get_cache
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_cache().clear()


@pytest.mark.asyncio
async def test_decimal_precision_preserved(session: AsyncSession, schema: None) -> None:
    # 1/3-ish — a value a float would round.
    raw = "0.123456789012345"
    await SettingsService.set(
        "cost_engine.power_cost_per_kwh",
        raw,
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    val = await SettingsService.get("cost_engine.power_cost_per_kwh", session=session)
    assert isinstance(val, Decimal)
    assert val == Decimal(raw)


@pytest.mark.asyncio
async def test_decimal_stored_as_string_not_float(session: AsyncSession, schema: None) -> None:
    await SettingsService.set(
        "cost_engine.labor_rate_per_hour",
        Decimal("25.50"),
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    row = (
        await session.execute(
            select(Setting).where(Setting.key == "cost_engine.labor_rate_per_hour")
        )
    ).scalar_one()
    # Strings, not floats. If this ever drifts to `float`, JSON precision
    # will betray us downstream.
    assert isinstance(row.value, str)
    assert row.value == "25.50"


@pytest.mark.asyncio
async def test_decimal_trailing_zeros_preserved(session: AsyncSession, schema: None) -> None:
    """``25.00`` and ``25`` are distinct Decimals; we preserve the form
    the operator typed in."""
    await SettingsService.set(
        "cost_engine.labor_rate_per_hour",
        "25.00",
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    val = await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    assert str(val) == "25.00"
