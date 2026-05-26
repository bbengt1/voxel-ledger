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
    PrinterCostParams,
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
    printer_cost_params: dict[uuid.UUID, PrinterCostParams] | None = None,
    power_cost_per_kwh: Decimal = Decimal("0"),
    failure_rate: Decimal = Decimal("0"),
) -> CalcContext:
    return CalcContext(
        material_cost_per_gram=material_costs or {},
        supply_unit_cost=supply_costs or {},
        labor_rate_per_hour=labor_rate,
        machine_rate_per_hour=machine_overrides or {},
        default_machine_rate_per_hour=default_machine_rate,
        overhead_percent=overhead,
        default_margin_percent=margin,
        printer_cost_params=printer_cost_params or {},
        power_cost_per_kwh=power_cost_per_kwh,
        failure_rate=failure_rate,
    )


def test_single_plate_known_values() -> None:
    """Hand-computed expected outputs.

    1 plate, 2 parts/set, 60 min print, 90 min setup (operator-attended),
    10g of one material at $0.05/g. Labor $60/h, machine $3/h.
    quantity_ordered=2 → 1 set.
    """
    material = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=2,
                print_minutes=60,
                print_grams_by_material={material: Decimal("10")},
                setup_minutes=90,
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
    # labor = 90/60 * 60 = 90.00 (print time is unattended; not billed)
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
                setup_minutes=60,
                assigned_printer_ids=[],
            ),
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={m: Decimal("5")},
                setup_minutes=60,
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
    # Each plate: 5g * $1 = $5 material; 60min setup * $60/h = $60 labor. Two plates.
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
                setup_minutes=60,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=3,
    )
    ctx = _ctx(labor_rate=Decimal("60"), default_machine_rate=Decimal("0"))
    result = calculate(inputs, ctx)
    assert result.sets_required == 2
    # 2 runs * 60min setup / 60 * $60/h = $120 labor.
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
                setup_minutes=60,
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
                setup_minutes=60,
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


# ---------------------------------------------------------------------------
# #249 — per-printer cost params, failure-rate buffer
# ---------------------------------------------------------------------------


def test_per_printer_cost_params_replace_flat_machine_rate() -> None:
    """Snapmaker U1 from issue #249.

    14.75-hour print, 296.67 g silk PLA at $17.99/kg, 5-year depreciation
    (300 hr/yr, $899 - $200 salvage), preheat 18 min at 140W, electricity
    $0.17/kWh, 10% failure buffer.

    Math (no rounding to Grok's $0.50/hr — uses the actual derived rate):

    - filament = 296.67 × $17.99/1000 = $5.336213
    - electricity = (885/60) × (127/1000) × $0.17 = $0.318504
    - preheat = (18/60) × (140/1000) × $0.17 = $0.007140
    - depreciation = 14.75 × ($699 / (5×300)) = 14.75 × $0.466 = $6.873500
    - subtotal direct = $12.535357
    - failure 10% = $1.253536 → direct $13.788893
    - overhead 0% → total = $13.79
    """
    material = uuid.uuid4()
    printer = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=885,
                print_grams_by_material={material: Decimal("296.67")},
                setup_minutes=0,
                assigned_printer_ids=[printer],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        material_costs={material: Decimal("0.01799")},
        labor_rate=Decimal("0"),
        default_machine_rate=Decimal("999"),  # would explode if used
        printer_cost_params={
            printer: PrinterCostParams(
                power_draw_watts=127,
                purchase_price=Decimal("899"),
                salvage_value=Decimal("200"),
                lifespan_years=5,
                annual_print_hours=300,
                preheat_minutes=18,
                preheat_power_watts=140,
            )
        },
        power_cost_per_kwh=Decimal("0.17"),
        failure_rate=Decimal("0.10"),
    )
    result = calculate(inputs, ctx)

    assert result.material_cost == Decimal("5.34")
    assert result.electricity_cost == Decimal("0.32")
    assert result.preheat_cost == Decimal("0.01")
    assert result.depreciation_cost == Decimal("6.87")
    # machine = electricity + preheat + depreciation = 0.318504 + 0.007140 + 6.8735 = 7.199144 → 7.20
    assert result.machine_cost == Decimal("7.20")
    # failure adj = (5.336213 + 0.318504 + 0.00714 + 6.8735) × 0.10 = 1.253536 → 1.25
    assert result.failure_adjustment_cost == Decimal("1.25")
    # total = 12.535357 + 1.253536 = 13.788893 → 13.79
    assert result.total_cost == Decimal("13.79")


def test_printer_without_full_cost_params_falls_back_to_flat_rate() -> None:
    """Missing cost params → flat machine_rate, breakdown stays zero."""
    printer = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={},
                setup_minutes=0,
                assigned_printer_ids=[printer],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        labor_rate=Decimal("0"),
        default_machine_rate=Decimal("4"),
        printer_cost_params={
            # Has wattage but no depreciation inputs → not "full".
            printer: PrinterCostParams(power_draw_watts=127)
        },
        power_cost_per_kwh=Decimal("0.17"),
    )
    result = calculate(inputs, ctx)
    # Flat-rate path: 1h × $4 = $4.00.
    assert result.machine_cost == Decimal("4.00")
    assert result.electricity_cost == Decimal("0.00")
    assert result.preheat_cost == Decimal("0.00")
    assert result.depreciation_cost == Decimal("0.00")


def test_failure_rate_applies_to_flat_rate_path_too() -> None:
    m = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={m: Decimal("10")},
                setup_minutes=0,
                assigned_printer_ids=[],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        material_costs={m: Decimal("1.00")},
        labor_rate=Decimal("0"),
        default_machine_rate=Decimal("0"),
        failure_rate=Decimal("0.10"),
    )
    result = calculate(inputs, ctx)
    # 10g × $1 = $10 material. Failure adj 10% = $1.00. Total $11.00.
    assert result.material_cost == Decimal("10.00")
    assert result.failure_adjustment_cost == Decimal("1.00")
    assert result.total_cost == Decimal("11.00")


def test_multi_printer_picks_lowest_derived_per_hour() -> None:
    """When all assigned printers have full cost params, use the lowest
    derived (electricity + depreciation) per-hour cost."""
    cheap = uuid.uuid4()
    expensive = uuid.uuid4()
    inputs = CalcInputs(
        plates=[
            PlateInput(
                parts_per_set=1,
                print_minutes=60,
                print_grams_by_material={},
                setup_minutes=0,
                assigned_printer_ids=[cheap, expensive],
            )
        ],
        quantity_ordered=1,
    )
    ctx = _ctx(
        labor_rate=Decimal("0"),
        default_machine_rate=Decimal("999"),
        printer_cost_params={
            cheap: PrinterCostParams(
                power_draw_watts=100,
                purchase_price=Decimal("500"),
                salvage_value=Decimal("100"),
                lifespan_years=5,
                annual_print_hours=400,
            ),
            expensive: PrinterCostParams(
                power_draw_watts=300,
                purchase_price=Decimal("5000"),
                salvage_value=Decimal("500"),
                lifespan_years=4,
                annual_print_hours=300,
            ),
        },
        power_cost_per_kwh=Decimal("0.15"),
    )
    result = calculate(inputs, ctx)
    # cheap: electricity=(100/1000)*0.15=$0.015/hr, dep=400/2000=$0.20/hr → $0.215/hr
    # expensive: electricity=(300/1000)*0.15=$0.045/hr, dep=4500/1200=$3.75/hr → $3.795/hr
    # 1 hour → $0.22
    assert result.machine_cost == Decimal("0.22")
