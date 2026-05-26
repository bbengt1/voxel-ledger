"""Pure-function cost calculator (Phase 5.3, #79).

Deterministic over ``(CalcInputs, CalcContext)``. No DB access, no I/O.
Decimal-only math; floats never enter the pipeline.

Sign conventions (forever decisions — encoded here, documented in the PR
that lands this module):

- All cost values are **positive** ``Decimal``\\s.
- ``suggested_unit_price = cost_per_piece * (1 + default_margin_percent)``
  quantized to 2 decimal places (USD cents).
- ``material_cost`` per plate run = ``sum(grams * cost_per_gram)``. Across
  plate runs and across plates: sum.
- ``labor_cost`` per plate run = ``(setup_minutes / 60) *
  labor_rate_per_hour``. 3D printing is unattended — only the operator
  time (setup, bed prep, post-processing, removal) is billed at the
  labor rate. Shops that pay an operator to babysit the printer should
  push that time into ``setup_minutes`` directly.
- ``machine_cost`` per plate run = ``(print_minutes / 60) *
  machine_rate(assigned_printer)``. If the plate has multiple printers
  assigned, we use the **lowest** rate among them — the operator will
  pick the cheapest available printer at scheduling time, so the cost
  estimate uses the floor of that decision.
- ``overhead_cost = overhead_percent * (material_cost + supply_cost +
  labor_cost + machine_cost)``. Overhead is applied to **direct costs
  only**, never to itself or to margin.

Quantization:

- Interior arithmetic accumulates at 6 decimal places (matching the
  ``Numeric(18, 6)`` storage precision of materials / rates).
- User-facing money values (``total_cost``, ``cost_per_piece``,
  ``suggested_unit_price``, the per-plate breakdown) quantize to 2
  decimal places at the boundary.

Sets math:

- ``pieces_per_set`` = sum of ``parts_per_set`` across plates. (One full
  set requires one run of every plate; each plate contributes its
  ``parts_per_set`` to the set's piece count.)
- ``sets_required`` = ``ceil(quantity_ordered / pieces_per_set)``, with
  a floor of 1 when ``quantity_ordered > 0`` and ``pieces_per_set > 0``.
- Plate runs per plate = ``sets_required`` (one run per set).
- ``quantity_ordered == 0`` → all costs zero; ``sets_required = 0``.
- ``pieces_per_set == 0`` (no plates) → all costs zero.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# Quantization templates. ``Decimal('0.000001')`` quantizes to 6 places,
# ``Decimal('0.01')`` to 2. Using string literals keeps these unambiguous
# under Python's Decimal context.
_Q_INTERIOR = Decimal("0.000001")
_Q_MONEY = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_SIXTY = Decimal("60")


def _q6(value: Decimal) -> Decimal:
    """Quantize to 6 decimal places, banker-safe via ROUND_HALF_UP."""
    return value.quantize(_Q_INTERIOR, rounding=ROUND_HALF_UP)


def _q2(value: Decimal) -> Decimal:
    """Quantize to 2 decimal places — user-facing money rounding."""
    return value.quantize(_Q_MONEY, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlateInput:
    """One plate's contribution to a calculation.

    Mirrors the shape of an :class:`app.models.plate.Plate` row but is a
    pure value object — the calculator never reaches back to the DB.
    """

    parts_per_set: int
    print_minutes: int
    print_grams_by_material: dict[uuid.UUID, Decimal]
    setup_minutes: int
    assigned_printer_ids: list[uuid.UUID]


@dataclass(frozen=True)
class CalcInputs:
    """The proposed job shape to cost out."""

    plates: list[PlateInput]
    quantity_ordered: int


@dataclass(frozen=True)
class PrinterCostParams:
    """Per-printer cost-engine inputs derived from the Printer row (#249).

    All fields optional. When the full set is present the calculator
    derives a per-hour machine cost from electricity + depreciation
    instead of the flat ``machine_rate_per_hour``. Preheat is its own
    one-shot-per-run line. ``power_draw_watts`` is the printing-time
    average; ``preheat_power_watts`` is the higher draw during the
    initial warmup.
    """

    power_draw_watts: int | None = None
    purchase_price: Decimal | None = None
    salvage_value: Decimal | None = None
    lifespan_years: int | None = None
    annual_print_hours: int | None = None
    preheat_minutes: int | None = None
    preheat_power_watts: int | None = None


@dataclass(frozen=True)
class CalcContext:
    """Snapshot of every cost input at calc time.

    Loaded once per request by :class:`CostEngineService.load_context`.
    The calculator only reads from this — never the DB.
    """

    material_cost_per_gram: dict[uuid.UUID, Decimal]
    supply_unit_cost: dict[uuid.UUID, Decimal]
    labor_rate_per_hour: Decimal
    machine_rate_per_hour: dict[uuid.UUID, Decimal]
    # Default machine rate (from #4.5 default Rate or #1.5 setting) used
    # when a plate's assigned printer has no per-printer override and
    # also as the fallback for plates with no printer assigned.
    default_machine_rate_per_hour: Decimal
    # Decimal fractions (e.g. ``Decimal("0.15")`` for 15%). The service
    # converts from the registry's percent-of-100 representation.
    overhead_percent: Decimal
    default_margin_percent: Decimal
    # #249 — per-printer cost params keyed by printer_id. When a plate's
    # assigned printer has a full set of cost params, the calculator
    # uses derived electricity + depreciation + preheat instead of the
    # flat ``machine_rate_per_hour``.
    printer_cost_params: dict[uuid.UUID, PrinterCostParams] = field(default_factory=dict)
    # Electricity rate in USD per kWh (``cost_engine.power_cost_per_kwh``).
    power_cost_per_kwh: Decimal = field(default_factory=lambda: Decimal("0"))
    # Failure buffer (decimal fraction; e.g. ``Decimal("0.10")`` = 10%).
    # Applied to (material + supply + labor + machine) before overhead.
    failure_rate: Decimal = field(default_factory=lambda: Decimal("0"))


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerPlateCost:
    """Per-plate breakdown of the costs that rolled up into the total.

    Values reflect the cost across **all runs of this plate for this job**
    (i.e. ``per_run_cost * sets_required``).
    """

    plate_index: int
    parts_per_set: int
    runs: int
    material_cost: Decimal
    labor_cost: Decimal
    machine_cost: Decimal


@dataclass(frozen=True)
class CalcResult:
    """Full breakdown returned by :func:`calculate`."""

    pieces_per_set: int
    sets_required: int
    material_cost: Decimal
    supply_cost: Decimal
    labor_cost: Decimal
    machine_cost: Decimal
    overhead_cost: Decimal
    total_cost: Decimal
    cost_per_piece: Decimal
    suggested_unit_price: Decimal
    # #249 itemized breakdown. These three sum into ``machine_cost``
    # when the plate's assigned printer carries per-printer cost params;
    # otherwise they're zero and ``machine_cost`` is the flat-rate
    # derivation. ``failure_adjustment_cost`` is the amount added by the
    # failure-rate buffer (already folded into ``total_cost``).
    electricity_cost: Decimal = field(default_factory=lambda: Decimal("0.00"))
    preheat_cost: Decimal = field(default_factory=lambda: Decimal("0.00"))
    depreciation_cost: Decimal = field(default_factory=lambda: Decimal("0.00"))
    failure_adjustment_cost: Decimal = field(default_factory=lambda: Decimal("0.00"))
    per_plate: list[PerPlateCost] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Calculation
# ---------------------------------------------------------------------------


def _ceil_div(numerator: int, denominator: int) -> int:
    """Integer ceiling division. Returns 0 when either operand is 0."""
    if numerator <= 0 or denominator <= 0:
        return 0
    return math.ceil(numerator / denominator)


def _machine_rate_for_plate(plate: PlateInput, ctx: CalcContext) -> Decimal:
    """Resolve the machine rate for a plate's run.

    Multi-printer plates use the **lowest** rate among assigned printers
    — the operator will pick the cheapest available printer, so cost
    estimates are computed against that floor. Plates with no assigned
    printer fall through to the default machine rate.
    """
    if not plate.assigned_printer_ids:
        return ctx.default_machine_rate_per_hour
    candidate_rates: list[Decimal] = []
    for printer_id in plate.assigned_printer_ids:
        rate = ctx.machine_rate_per_hour.get(printer_id)
        if rate is None:
            rate = ctx.default_machine_rate_per_hour
        candidate_rates.append(rate)
    return min(candidate_rates)


def _has_full_cost_params(p: PrinterCostParams) -> bool:
    """True when the printer carries enough fields to derive a per-hour
    cost from electricity + depreciation."""
    return (
        p.power_draw_watts is not None
        and p.power_draw_watts > 0
        and p.purchase_price is not None
        and p.purchase_price > 0
        and p.salvage_value is not None
        and p.lifespan_years is not None
        and p.lifespan_years > 0
        and p.annual_print_hours is not None
        and p.annual_print_hours > 0
    )


def _component_costs_for_plate(
    plate: PlateInput, ctx: CalcContext
) -> tuple[Decimal, Decimal, Decimal] | None:
    """Per-run (electricity, preheat, depreciation) when the chosen
    printer has full cost params; else None and the caller falls back to
    the flat ``machine_rate_per_hour`` path.

    Multi-printer plates pick the printer with the **lowest** derived
    per-hour cost (electricity + depreciation), matching the existing
    floor convention in ``_machine_rate_for_plate``. If any assigned
    printer is missing cost params we abort to the flat-rate path
    rather than mixing methodologies for the same plate.
    """
    if not plate.assigned_printer_ids:
        return None
    candidates: list[tuple[Decimal, PrinterCostParams]] = []
    for printer_id in plate.assigned_printer_ids:
        params = ctx.printer_cost_params.get(printer_id)
        if params is None or not _has_full_cost_params(params):
            return None
        # ``_has_full_cost_params`` guarantees non-None on the fields we
        # touch; assertions keep mypy/pyright happy without runtime cost.
        assert params.power_draw_watts is not None
        assert params.purchase_price is not None
        assert params.salvage_value is not None
        assert params.lifespan_years is not None
        assert params.annual_print_hours is not None
        electricity_per_hour = (
            Decimal(params.power_draw_watts) / Decimal("1000")
        ) * ctx.power_cost_per_kwh
        lifetime_hours = Decimal(params.lifespan_years) * Decimal(params.annual_print_hours)
        depreciation_per_hour = (
            (params.purchase_price - params.salvage_value) / lifetime_hours
            if lifetime_hours > 0
            else _ZERO
        )
        candidates.append((electricity_per_hour + depreciation_per_hour, params))
    # Pick the lowest-cost printer among assigned. min() with tuples
    # compares the first element first, which is what we want.
    _, chosen = min(candidates, key=lambda c: c[0])
    assert chosen.power_draw_watts is not None
    assert chosen.purchase_price is not None
    assert chosen.salvage_value is not None
    assert chosen.lifespan_years is not None
    assert chosen.annual_print_hours is not None

    print_hours = Decimal(plate.print_minutes) / _SIXTY
    electricity_per_hour = (
        Decimal(chosen.power_draw_watts) / Decimal("1000")
    ) * ctx.power_cost_per_kwh
    electricity = _q6(print_hours * electricity_per_hour)

    preheat_minutes = chosen.preheat_minutes or 0
    preheat_power = chosen.preheat_power_watts or chosen.power_draw_watts
    if preheat_minutes > 0 and preheat_power > 0:
        preheat = _q6(
            (Decimal(preheat_minutes) / _SIXTY)
            * (Decimal(preheat_power) / Decimal("1000"))
            * ctx.power_cost_per_kwh
        )
    else:
        preheat = _ZERO

    lifetime_hours = Decimal(chosen.lifespan_years) * Decimal(chosen.annual_print_hours)
    depreciation_per_hour = (
        (chosen.purchase_price - chosen.salvage_value) / lifetime_hours
        if lifetime_hours > 0
        else _ZERO
    )
    depreciation = _q6(print_hours * depreciation_per_hour)
    return electricity, preheat, depreciation


def _plate_material_cost_per_run(plate: PlateInput, ctx: CalcContext) -> Decimal:
    """Sum of (grams * cost_per_gram) across the plate's materials."""
    total = _ZERO
    for material_id, grams in plate.print_grams_by_material.items():
        grams_dec = grams if isinstance(grams, Decimal) else Decimal(str(grams))
        if grams_dec <= 0:
            continue
        cost_per_gram = ctx.material_cost_per_gram.get(material_id, _ZERO)
        total += grams_dec * cost_per_gram
    return _q6(total)


def calculate(inputs: CalcInputs, ctx: CalcContext) -> CalcResult:
    """Pure cost calculation.

    See module docstring for sign conventions and quantization rules.
    """
    plates = list(inputs.plates)
    pieces_per_set = sum(p.parts_per_set for p in plates)
    sets_required = _ceil_div(inputs.quantity_ordered, pieces_per_set)

    # Short-circuit: no work to do.
    if sets_required == 0 or pieces_per_set == 0:
        zero_result = CalcResult(
            pieces_per_set=pieces_per_set,
            sets_required=sets_required,
            material_cost=_q2(_ZERO),
            supply_cost=_q2(_ZERO),
            labor_cost=_q2(_ZERO),
            machine_cost=_q2(_ZERO),
            overhead_cost=_q2(_ZERO),
            total_cost=_q2(_ZERO),
            cost_per_piece=_q2(_ZERO),
            suggested_unit_price=_q2(_ZERO),
            per_plate=[
                PerPlateCost(
                    plate_index=idx,
                    parts_per_set=p.parts_per_set,
                    runs=0,
                    material_cost=_q2(_ZERO),
                    labor_cost=_q2(_ZERO),
                    machine_cost=_q2(_ZERO),
                )
                for idx, p in enumerate(plates)
            ],
        )
        return zero_result

    runs_per_plate = sets_required  # one run per set, one run per plate per set

    # Accumulators at 6-place precision.
    total_material = _ZERO
    total_labor = _ZERO
    total_machine = _ZERO
    total_electricity = _ZERO
    total_preheat = _ZERO
    total_depreciation = _ZERO
    per_plate_rows: list[PerPlateCost] = []

    labor_rate = ctx.labor_rate_per_hour

    for idx, plate in enumerate(plates):
        material_per_run = _plate_material_cost_per_run(plate, ctx)
        plate_material = _q6(material_per_run * Decimal(runs_per_plate))

        # Labor: setup + operator-attended time only. Print time is
        # unattended in a typical print shop and is captured by the
        # machine rate (or per-printer depreciation + electricity).
        print_hours = Decimal(plate.print_minutes) / _SIXTY
        setup_hours = Decimal(plate.setup_minutes) / _SIXTY
        labor_per_run = _q6(setup_hours * labor_rate)
        plate_labor = _q6(labor_per_run * Decimal(runs_per_plate))

        # Machine: when the chosen printer has full per-printer cost
        # params, derive machine cost from electricity + depreciation +
        # preheat; otherwise fall back to the flat ``machine_rate``.
        components = _component_costs_for_plate(plate, ctx)
        if components is not None:
            electricity_per_run, preheat_per_run, depreciation_per_run = components
            machine_per_run = electricity_per_run + preheat_per_run + depreciation_per_run
            total_electricity += _q6(electricity_per_run * Decimal(runs_per_plate))
            total_preheat += _q6(preheat_per_run * Decimal(runs_per_plate))
            total_depreciation += _q6(depreciation_per_run * Decimal(runs_per_plate))
        else:
            machine_rate = _machine_rate_for_plate(plate, ctx)
            machine_per_run = _q6(print_hours * machine_rate)
        plate_machine = _q6(machine_per_run * Decimal(runs_per_plate))

        total_material += plate_material
        total_labor += plate_labor
        total_machine += plate_machine

        per_plate_rows.append(
            PerPlateCost(
                plate_index=idx,
                parts_per_set=plate.parts_per_set,
                runs=runs_per_plate,
                material_cost=_q2(plate_material),
                labor_cost=_q2(plate_labor),
                machine_cost=_q2(plate_machine),
            )
        )

    # Supplies aren't tied to individual plates today — the calc context
    # carries any supply costs the service decides to roll in. For now,
    # the per-unit supply cost dict is summed straight through (callers
    # whose proposal has no supplies attached will pass an empty dict,
    # which yields zero). Quantity-scaled supply costs can be wired in
    # via the service in a follow-up without changing this signature.
    total_supply = _ZERO
    for unit_cost in ctx.supply_unit_cost.values():
        total_supply += unit_cost
    total_supply = _q6(total_supply)

    direct_costs_pre_failure = total_material + total_supply + total_labor + total_machine
    failure_adjustment = _q6(direct_costs_pre_failure * ctx.failure_rate)
    direct_costs = direct_costs_pre_failure + failure_adjustment
    total_overhead = _q6(direct_costs * ctx.overhead_percent)

    total_cost = _q6(direct_costs + total_overhead)

    # Cost per piece is total / pieces produced. Pieces produced =
    # pieces_per_set * sets_required (one full set per sets_required).
    pieces_total = Decimal(pieces_per_set * sets_required)
    cost_per_piece_raw = total_cost / pieces_total if pieces_total > 0 else _ZERO
    cost_per_piece = _q6(cost_per_piece_raw)

    suggested_raw = cost_per_piece * (_ONE + ctx.default_margin_percent)

    return CalcResult(
        pieces_per_set=pieces_per_set,
        sets_required=sets_required,
        material_cost=_q2(total_material),
        supply_cost=_q2(total_supply),
        labor_cost=_q2(total_labor),
        machine_cost=_q2(total_machine),
        overhead_cost=_q2(total_overhead),
        total_cost=_q2(total_cost),
        cost_per_piece=_q2(cost_per_piece),
        suggested_unit_price=_q2(suggested_raw),
        electricity_cost=_q2(total_electricity),
        preheat_cost=_q2(total_preheat),
        depreciation_cost=_q2(total_depreciation),
        failure_adjustment_cost=_q2(failure_adjustment),
        per_plate=per_plate_rows,
    )


__all__ = [
    "CalcContext",
    "CalcInputs",
    "CalcResult",
    "PerPlateCost",
    "PlateInput",
    "PrinterCostParams",
    "calculate",
]
