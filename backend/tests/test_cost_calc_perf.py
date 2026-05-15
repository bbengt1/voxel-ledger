"""Performance smoke test for the cost-calc endpoint (Phase 5.3, #79).

Marked ``@pytest.mark.benchmark`` — informational only, not part of the
default pytest run. Asserts 100 sequential calls complete in under 10
seconds (i.e. p50 < 100ms). The full v2 perf budget (<200ms p95 against
a realistic catalog) is enforced separately in CI / staging; this is a
guardrail that catches obvious regressions during development.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from app.models import Base
from app.models.material import Material
from app.models.rate import Rate, RateKind
from app.models.supply import Supply
from app.services.cost_engine.calculator import CalcInputs, PlateInput
from app.services.cost_engine.service import CostEngineService
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(autouse=True)
async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_realistic_catalog(session: AsyncSession) -> list[uuid.UUID]:
    """Seed ~50 materials, 30 supplies, 10 rates. Returns material IDs."""
    material_ids: list[uuid.UUID] = []
    for i in range(50):
        m = Material(
            name=f"Material {i}",
            material_type="PLA",
            current_cost_per_gram=Decimal(f"0.0{(i % 9) + 1}"),
        )
        session.add(m)
        material_ids.append(m.id)
    for i in range(30):
        session.add(
            Supply(
                name=f"Supply {i}",
                unit="ea",
                unit_cost=Decimal("0.50"),
            )
        )
    session.add_all(
        [
            Rate(
                name="Labor default",
                kind=RateKind.LABOR,
                value=Decimal("25.00"),
                is_default_for_kind=True,
            ),
            Rate(
                name="Machine default",
                kind=RateKind.MACHINE,
                value=Decimal("1.00"),
                is_default_for_kind=True,
            ),
            Rate(
                name="Overhead default",
                kind=RateKind.OVERHEAD,
                value=Decimal("0.15"),
                is_default_for_kind=True,
            ),
        ]
    )
    await session.commit()
    return material_ids


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_100_calculations_under_10_seconds(session: AsyncSession) -> None:
    """100 sequential ``calculate_for_inputs`` calls < 10 s on SQLite."""
    material_ids = await _seed_realistic_catalog(session)

    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=2,
                print_minutes=60,
                print_grams_by_material={
                    material_ids[0]: Decimal("10"),
                    material_ids[1]: Decimal("5"),
                },
                setup_minutes=15,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=10,
    )

    start = time.perf_counter()
    for _ in range(100):
        await CostEngineService.calculate_for_inputs(inputs, session=session)
    elapsed = time.perf_counter() - start

    assert elapsed < 10.0, f"100 calc calls took {elapsed:.2f}s (>10s)"
