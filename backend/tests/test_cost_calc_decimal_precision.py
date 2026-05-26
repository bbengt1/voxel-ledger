"""Decimal-precision tests for the cost calculator (Phase 5.3, #79).

Exercises values that hit the boundaries of Numeric(18, 6) storage and
confirms no float drift sneaks into the pipeline.
"""

from __future__ import annotations

import uuid
import warnings
from decimal import Decimal

from app.services.cost_engine.calculator import (
    CalcContext,
    CalcInputs,
    PlateInput,
    calculate,
)


def _ctx(**kwargs: Decimal) -> CalcContext:
    return CalcContext(
        material_cost_per_gram=kwargs.get("material_costs", {}) or {},
        supply_unit_cost={},
        labor_rate_per_hour=kwargs.get("labor_rate", Decimal("0")),
        machine_rate_per_hour={},
        default_machine_rate_per_hour=kwargs.get("machine_rate", Decimal("0")),
        overhead_percent=kwargs.get("overhead", Decimal("0")),
        default_margin_percent=kwargs.get("margin", Decimal("0")),
    )


def test_six_place_material_cost_no_drift() -> None:
    material = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=0,
                print_grams_by_material={material: Decimal("123.456789")},
                setup_minutes=0,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(material_costs={material: Decimal("0.123456")})
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any DecimalException-class warning fails the test
        result = calculate(inputs, ctx)

    # 123.456789 * 0.123456 = 15.241456... — quantized to 2 places.
    expected_material = (Decimal("123.456789") * Decimal("0.123456")).quantize(Decimal("0.01"))
    assert result.material_cost == expected_material


def test_repeated_summation_does_not_drift() -> None:
    """Sum 1000 plates of $0.0001/g * 1g each. With floats this would drift;
    with Decimal it's exactly $0.10."""
    material = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=0,
                print_grams_by_material={material: Decimal("1")},
                setup_minutes=0,
                assigned_printer_ids=[],
            )
            for _ in range(1000)
        ],
        quantity_ordered=1000,
    )
    ctx = _ctx(material_costs={material: Decimal("0.0001")})
    result = calculate(inputs, ctx)
    # 1000 plates x 1g x $0.0001 = $0.10.
    assert result.material_cost == Decimal("0.10")


def test_no_float_types_in_result() -> None:
    material = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={material: Decimal("1.5")},
                setup_minutes=0,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        material_costs={material: Decimal("0.5")},
        labor_rate=Decimal("60"),
        machine_rate=Decimal("3"),
        overhead=Decimal("0.15"),
        margin=Decimal("0.30"),
    )
    result = calculate(inputs, ctx)
    for field in (
        result.material_cost,
        result.supply_cost,
        result.labor_cost,
        result.machine_cost,
        result.overhead_cost,
        result.total_cost,
        result.cost_per_piece,
        result.suggested_unit_price,
    ):
        assert isinstance(field, Decimal)
        # Confirm 2-decimal-place exposure.
        assert -field.as_tuple().exponent <= 2
    for row in result.per_plate:
        assert isinstance(row.material_cost, Decimal)
        assert isinstance(row.labor_cost, Decimal)
        assert isinstance(row.machine_cost, Decimal)


def test_high_value_does_not_overflow() -> None:
    """Numeric(18,6) gives us up to 12 digits before the decimal point.
    Use a still-large but safe value to confirm the pipeline doesn't
    silently truncate or coerce."""
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=0,
                print_grams_by_material={},
                setup_minutes=60,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        labor_rate=Decimal("1000000"),
        machine_rate=Decimal("0"),
    )
    result = calculate(inputs, ctx)
    assert result.labor_cost == Decimal("1000000.00")
    assert result.total_cost == Decimal("1000000.00")
