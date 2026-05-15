"""Pure-function tests for the cost calculator (Phase 5.3, #79).

These tests only exercise the deterministic ``calculate`` function with
hand-built ``CalcInputs`` and ``CalcContext`` values. No DB, no I/O — if
they ever require a fixture beyond ``Decimal``s, the calculator has
leaked a side effect.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.services.cost_engine.calculator import (
    CalcContext,
    CalcInputs,
    PlateInput,
    calculate,
)

_ZERO = Decimal("0")


def _ctx(
    *,
    material_costs: dict[uuid.UUID, Decimal] | None = None,
    labor_rate: Decimal = Decimal("60"),
    default_machine_rate: Decimal = Decimal("3"),
    machine_overrides: dict[uuid.UUID, Decimal] | None = None,
    overhead: Decimal = Decimal("0"),
    margin: Decimal = Decimal("0"),
    supply_costs: dict[uuid.UUID, Decimal] | None = None,
) -> CalcContext:
    return CalcContext(
        material_cost_per_gram=material_costs or {},
        supply_unit_cost=supply_costs or {},
        labor_rate_per_hour=labor_rate,
        machine_rate_per_hour=machine_overrides or {},
        default_machine_rate_per_hour=default_machine_rate,
        overhead_percent=overhead,
        default_margin_percent=margin,
    )


def test_single_plate_known_values() -> None:
    """Hand-computed expected outputs.

    1 plate, 2 parts/set, 60 min print, 30 min setup, 10g of one material
    at $0.05/g. Labor $60/h, machine $3/h. quantity_ordered=2 → 1 set.
    """
    material = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=2,
                print_minutes=60,
                print_grams_by_material={material: Decimal("10")},
                setup_minutes=30,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=2,
    )
    ctx = _ctx(material_costs={material: Decimal("0.05")})
    result = calculate(inputs, ctx)

    assert result.pieces_per_set == 2
    assert result.sets_required == 1
    # material = 10 * 0.05 = 0.50
    assert result.material_cost == Decimal("0.50")
    # labor = (60+30)/60 * 60 = 90.00
    assert result.labor_cost == Decimal("90.00")
    # machine = 60/60 * 3 = 3.00
    assert result.machine_cost == Decimal("3.00")
    assert result.overhead_cost == Decimal("0.00")
    # total = 93.50
    assert result.total_cost == Decimal("93.50")
    # cost_per_piece = 93.50 / 2 = 46.75
    assert result.cost_per_piece == Decimal("46.75")
    # margin 0 → suggested == cost
    assert result.suggested_unit_price == Decimal("46.75")
    assert len(result.per_plate) == 1


def test_multi_plate_aggregates_across_plates() -> None:
    m = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={m: Decimal("5")},
                setup_minutes=0,
                assigned_printer_ids=[],
            ),
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={m: Decimal("5")},
                setup_minutes=0,
                assigned_printer_ids=[],
            ),
        ],
        quantity_ordered=2,
    )
    ctx = _ctx(
        material_costs={m: Decimal("1.00")},
        labor_rate=Decimal("60"),
        default_machine_rate=Decimal("0"),
    )
    result = calculate(inputs, ctx)
    assert result.pieces_per_set == 2
    assert result.sets_required == 1
    # Each plate: 5g * $1 = $5 material; 1h * $60 = $60 labor. Two plates.
    assert result.material_cost == Decimal("10.00")
    assert result.labor_cost == Decimal("120.00")
    assert result.total_cost == Decimal("130.00")
    assert len(result.per_plate) == 2


def test_multi_printer_uses_lowest_rate() -> None:
    fast = uuid.uuid4()
    slow = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={},
                setup_minutes=0,
                assigned_printer_ids=[fast, slow],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        labor_rate=Decimal("0"),
        default_machine_rate=Decimal("100"),
        machine_overrides={fast: Decimal("5"), slow: Decimal("10")},
    )
    result = calculate(inputs, ctx)
    # Lowest of (5, 10) wins → 60min/60 * 5 = 5.00.
    assert result.machine_cost == Decimal("5.00")


def test_zero_quantity_returns_zero_costs() -> None:
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=4,
                print_minutes=100,
                print_grams_by_material={},
                setup_minutes=10,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=0,
    )
    result = calculate(inputs, _ctx())
    assert result.sets_required == 0
    assert result.total_cost == Decimal("0.00")
    assert result.cost_per_piece == Decimal("0.00")
    assert result.suggested_unit_price == Decimal("0.00")


def test_partial_set_rounds_up() -> None:
    """quantity_ordered=3 with parts_per_set=2 needs 2 sets (4 pieces)."""
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=2,
                print_minutes=60,
                print_grams_by_material={},
                setup_minutes=0,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=3,
    )
    ctx = _ctx(labor_rate=Decimal("60"), default_machine_rate=Decimal("0"))
    result = calculate(inputs, ctx)
    assert result.sets_required == 2
    # 2 runs * 60min/60 * $60/h = $120 labor.
    assert result.labor_cost == Decimal("120.00")
    # cost_per_piece divides total by pieces_total = 4 pieces (not 3).
    assert result.cost_per_piece == Decimal("30.00")


def test_overhead_applied_to_direct_costs_only() -> None:
    inputs = CalcInputs(
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
    # $60 labor, $0 everything else, 50% overhead.
    ctx = _ctx(
        labor_rate=Decimal("60"),
        default_machine_rate=Decimal("0"),
        overhead=Decimal("0.5"),
    )
    result = calculate(inputs, ctx)
    assert result.labor_cost == Decimal("60.00")
    # Overhead = 50% of $60 direct = $30. NOT applied to itself.
    assert result.overhead_cost == Decimal("30.00")
    assert result.total_cost == Decimal("90.00")


def test_margin_applied_to_cost_per_piece() -> None:
    inputs = CalcInputs(
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
    ctx = _ctx(
        labor_rate=Decimal("100"),
        default_machine_rate=Decimal("0"),
        margin=Decimal("0.3"),
    )
    result = calculate(inputs, ctx)
    assert result.cost_per_piece == Decimal("100.00")
    # 100 * 1.30 = 130.00
    assert result.suggested_unit_price == Decimal("130.00")


def test_unknown_printer_falls_back_to_default_rate() -> None:
    """A printer not in the rate map uses the default machine rate."""
    unknown = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={},
                setup_minutes=0,
                assigned_printer_ids=[unknown],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        labor_rate=Decimal("0"),
        default_machine_rate=Decimal("7"),
    )
    result = calculate(inputs, ctx)
    assert result.machine_cost == Decimal("7.00")


def test_no_plates_yields_zero_pieces_and_zero_costs() -> None:
    inputs = CalcInputs(plates=[], quantity_ordered=5)
    result = calculate(inputs, _ctx())
    assert result.pieces_per_set == 0
    assert result.sets_required == 0
    assert result.total_cost == _ZERO.quantize(Decimal("0.01"))
