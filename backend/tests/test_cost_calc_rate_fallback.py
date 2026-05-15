"""Service-layer rate-resolution tests (Phase 5.3, #79).

Covers: a Rate row marked default wins; settings fallback wins when no
Rate row is default; overhead conversion from percent-of-100 to decimal
fraction.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.rate import Rate, RateKind
from app.services.cost_engine.calculator import CalcInputs, PlateInput
from app.services.cost_engine.service import CostEngineService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(autouse=True)
async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _simple_inputs() -> CalcInputs:
    return CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={},
                setup_minutes=0,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=1,
    )


@pytest.mark.asyncio
async def test_settings_fallback_when_no_default_rate(session: AsyncSession) -> None:
    """No Rate rows exist → calc uses the settings registry defaults
    (labor=25, machine=1, overhead=15%, margin=30%)."""
    ctx = await CostEngineService.load_context(session=session, plate_inputs=[])
    assert ctx.labor_rate_per_hour == Decimal("25.00")
    assert ctx.default_machine_rate_per_hour == Decimal("1.00")
    # Overhead: settings store 15.00 → calculator gets 0.15.
    assert ctx.overhead_percent == Decimal("0.15")
    assert ctx.default_margin_percent == Decimal("0.30")


@pytest.mark.asyncio
async def test_default_rate_row_wins_over_setting(session: AsyncSession) -> None:
    """A Rate row with is_default_for_kind=true overrides the setting."""
    session.add_all(
        [
            Rate(
                name="Labor default",
                kind=RateKind.LABOR,
                value=Decimal("99.00"),
                is_default_for_kind=True,
            ),
            Rate(
                name="Machine default",
                kind=RateKind.MACHINE,
                value=Decimal("4.00"),
                is_default_for_kind=True,
            ),
            Rate(
                name="Overhead default",
                kind=RateKind.OVERHEAD,
                value=Decimal("0.20"),
                is_default_for_kind=True,
            ),
        ]
    )
    await session.commit()

    ctx = await CostEngineService.load_context(session=session, plate_inputs=[])
    assert ctx.labor_rate_per_hour == Decimal("99.00")
    assert ctx.default_machine_rate_per_hour == Decimal("4.00")
    # Rate rows store overhead as the decimal fraction already.
    assert ctx.overhead_percent == Decimal("0.20")


@pytest.mark.asyncio
async def test_per_printer_machine_rate_loaded(session: AsyncSession) -> None:
    printer_id = uuid.uuid4()
    session.add_all(
        [
            Rate(
                name="Machine default",
                kind=RateKind.MACHINE,
                value=Decimal("5.00"),
                is_default_for_kind=True,
            ),
            Rate(
                name="Per-printer override",
                kind=RateKind.MACHINE,
                value=Decimal("12.00"),
                applies_to_printer_id=printer_id,
            ),
        ]
    )
    await session.commit()

    ctx = await CostEngineService.load_context(session=session, plate_inputs=[])
    assert ctx.machine_rate_per_hour[printer_id] == Decimal("12.00")
    assert ctx.default_machine_rate_per_hour == Decimal("5.00")


@pytest.mark.asyncio
async def test_calculate_for_inputs_uses_settings_fallback(
    session: AsyncSession,
) -> None:
    """End-to-end through the service with no Rate rows: pulls labor=25,
    machine=1, overhead=15%, margin=30% from settings."""
    inputs = _simple_inputs()
    result = await CostEngineService.calculate_for_inputs(inputs, session=session)
    # 1h labor @ $25 = $25.00, 1h machine @ $1 = $1.00. Direct = $26.00.
    # Overhead = 15% of $26 = $3.90. Total = $29.90.
    assert result.labor_cost == Decimal("25.00")
    assert result.machine_cost == Decimal("1.00")
    assert result.overhead_cost == Decimal("3.90")
    assert result.total_cost == Decimal("29.90")
    # margin 30% → suggested = 29.90 * 1.30 = 38.87.
    assert result.suggested_unit_price == Decimal("38.87")
