"""Cost engine service (Phase 5.3, #79).

DB-aware wrapper around :func:`app.services.cost_engine.calculator.calculate`.
The service is responsible for assembling a :class:`CalcContext` from:

  1. Phase 4.5 ``rate`` rows (``is_default_for_kind=true`` for labor /
     machine / overhead, plus per-printer machine overrides).
  2. Phase 1.5 settings (``cost_engine.labor_rate_per_hour``,
     ``cost_engine.machine_rate_per_hour``, ``cost_engine.overhead_percent``,
     ``cost_engine.default_margin_percent``) as the fallback when no
     Rate row carries the default.
  3. Per-material ``current_cost_per_gram`` from the materials catalog
     (maintained by the ``material_cost`` projection).
  4. Per-supply ``unit_cost`` from the supplies catalog.

The settings registry stores ``overhead_percent`` and ``default_margin_percent``
as a percentage out of 100 (e.g. ``Decimal("15.00")`` means 15%). The
calculator expects them as decimal fractions (e.g. ``Decimal("0.15")``),
so the service performs that conversion at the boundary.

Performance: the loader batches all material / supply / rate lookups so
the round trip is bounded — three SELECTs against material, supply, and
rate respectively, plus the settings reads (each cached).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material import Material
from app.models.printer import Printer
from app.models.rate import Rate, RateKind
from app.models.supply import Supply
from app.services.cost_engine.calculator import (
    CalcContext,
    CalcInputs,
    CalcResult,
    PlateInput,
    PrinterCostParams,
    calculate,
)
from app.services.jobs import JobNotFoundError
from app.services.jobs import get as get_job
from app.services.settings.service import SettingsService

_HUNDRED = Decimal("100")
_ZERO = Decimal("0")


class MissingRateConfigError(Exception):
    """Neither a default Rate row nor a settings value is available for a
    rate kind required by the cost engine.

    The settings registry has defaults for every cost-engine key so this
    should normally never fire — it's a defence-in-depth signal for
    setups where the registry was tampered with or the schema defaults
    were overridden out from under us.
    """


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------


async def _load_material_costs(
    session: AsyncSession, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    id_list = list({i for i in ids})
    if not id_list:
        return {}
    rows = (
        await session.execute(
            select(Material.id, Material.current_cost_per_gram).where(Material.id.in_(id_list))
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def _load_supply_costs(
    session: AsyncSession, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    id_list = list({i for i in ids})
    if not id_list:
        return {}
    rows = (
        await session.execute(select(Supply.id, Supply.unit_cost).where(Supply.id.in_(id_list)))
    ).all()
    return {row[0]: row[1] for row in rows}


async def _load_all_rates(session: AsyncSession) -> list[Rate]:
    stmt = select(Rate).where(Rate.is_archived.is_(False))
    return list((await session.execute(stmt)).scalars().all())


async def _resolve_labor_rate(rates: list[Rate], session: AsyncSession) -> Decimal:
    for r in rates:
        if r.kind == RateKind.LABOR and r.is_default_for_kind:
            return r.value
    fallback = await SettingsService.get("cost_engine.labor_rate_per_hour", session=session)
    if fallback is None:
        raise MissingRateConfigError(
            "configure a default labor rate (Phase 4.5 Rate or "
            "cost_engine.labor_rate_per_hour setting)"
        )
    return Decimal(str(fallback))


async def _resolve_default_machine_rate(rates: list[Rate], session: AsyncSession) -> Decimal:
    for r in rates:
        if r.kind == RateKind.MACHINE and r.is_default_for_kind and r.applies_to_printer_id is None:
            return r.value
    fallback = await SettingsService.get("cost_engine.machine_rate_per_hour", session=session)
    if fallback is None:
        raise MissingRateConfigError(
            "configure a default machine rate (Phase 4.5 Rate or "
            "cost_engine.machine_rate_per_hour setting)"
        )
    return Decimal(str(fallback))


def _resolve_per_printer_machine_rates(rates: list[Rate]) -> dict[uuid.UUID, Decimal]:
    """Map of printer_id → machine rate from per-printer Rate rows."""
    out: dict[uuid.UUID, Decimal] = {}
    for r in rates:
        if r.kind != RateKind.MACHINE:
            continue
        if r.applies_to_printer_id is None:
            continue
        # Last-write-wins is fine here — the catalog doesn't currently
        # enforce one rate per printer, so an explicit operator decision
        # picks which row "wins". The default-for-kind flag wins over
        # non-default duplicates.
        prior = out.get(r.applies_to_printer_id)
        if prior is None or r.is_default_for_kind:
            out[r.applies_to_printer_id] = r.value
    return out


async def _resolve_overhead_percent(rates: list[Rate], session: AsyncSession) -> Decimal:
    """Return overhead as a decimal fraction (e.g. 0.15 for 15%).

    The Rate row stores overhead as a decimal fraction directly (e.g.
    ``Decimal("0.15")``). The settings registry stores it as percent-
    of-100 (``Decimal("15.00")``); we divide by 100 at the boundary.
    """
    for r in rates:
        if r.kind == RateKind.OVERHEAD and r.is_default_for_kind:
            return r.value
    fallback = await SettingsService.get("cost_engine.overhead_percent", session=session)
    if fallback is None:
        raise MissingRateConfigError(
            "configure a default overhead rate (Phase 4.5 Rate or "
            "cost_engine.overhead_percent setting)"
        )
    # Settings registry: 15.00 means 15%. Calculator expects 0.15.
    return Decimal(str(fallback)) / _HUNDRED


async def _load_printer_cost_params(
    session: AsyncSession, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, PrinterCostParams]:
    """Snapshot per-printer cost-engine inputs (#249) for the given ids."""
    id_list = list({i for i in ids})
    if not id_list:
        return {}
    rows = (
        await session.execute(
            select(
                Printer.id,
                Printer.power_draw_watts,
                Printer.purchase_price,
                Printer.salvage_value,
                Printer.lifespan_years,
                Printer.annual_print_hours,
                Printer.preheat_minutes,
                Printer.preheat_power_watts,
            ).where(Printer.id.in_(id_list))
        )
    ).all()
    return {
        row[0]: PrinterCostParams(
            power_draw_watts=row[1],
            purchase_price=row[2],
            salvage_value=row[3],
            lifespan_years=row[4],
            annual_print_hours=row[5],
            preheat_minutes=row[6],
            preheat_power_watts=row[7],
        )
        for row in rows
    }


async def _resolve_power_cost_per_kwh(session: AsyncSession) -> Decimal:
    raw = await SettingsService.get("cost_engine.power_cost_per_kwh", session=session)
    if raw is None:
        return _ZERO
    return Decimal(str(raw))


async def _resolve_failure_rate(session: AsyncSession) -> Decimal:
    """Failure-rate buffer as a decimal fraction (e.g. 0.10 for 10%)."""
    raw = await SettingsService.get("cost_engine.failure_rate_percent", session=session)
    if raw is None:
        return _ZERO
    return Decimal(str(raw)) / _HUNDRED


async def _resolve_default_margin_percent(session: AsyncSession) -> Decimal:
    """Default margin as a decimal fraction (e.g. 0.30 for 30%).

    No Rate row encodes "margin" — it's a sales-side number, not a cost.
    Lives solely in the settings registry as percent-of-100.
    """
    raw = await SettingsService.get("cost_engine.default_margin_percent", session=session)
    if raw is None:
        return _ZERO
    return Decimal(str(raw)) / _HUNDRED


# ---------------------------------------------------------------------------
# Public service surface
# ---------------------------------------------------------------------------


class CostEngineService:
    """Async context-loader + delegator over the pure calculator."""

    @staticmethod
    async def load_context(*, session: AsyncSession, plate_inputs: list[PlateInput]) -> CalcContext:
        """Snapshot every cost input needed to calculate ``plate_inputs``."""
        material_ids: set[uuid.UUID] = set()
        for p in plate_inputs:
            material_ids.update(p.print_grams_by_material.keys())

        material_costs = await _load_material_costs(session, material_ids)
        # Materials referenced but missing from the catalog default to
        # zero cost — keeps the calc deterministic even when a draft
        # references a since-archived material; callers can detect this
        # via the missing key on the returned context if needed.
        for mid in material_ids:
            material_costs.setdefault(mid, _ZERO)

        # Supplies: today no plate carries supply usage, so we just
        # resolve an empty dict. Hook is here for the future when supply
        # consumption per job becomes a first-class input.
        supply_costs: dict[uuid.UUID, Decimal] = {}

        rates = await _load_all_rates(session)
        labor_rate = await _resolve_labor_rate(rates, session)
        default_machine_rate = await _resolve_default_machine_rate(rates, session)
        per_printer_rates = _resolve_per_printer_machine_rates(rates)
        overhead = await _resolve_overhead_percent(rates, session)
        margin = await _resolve_default_margin_percent(session)

        printer_ids: set[uuid.UUID] = set()
        for p in plate_inputs:
            printer_ids.update(p.assigned_printer_ids)
        printer_cost_params = await _load_printer_cost_params(session, printer_ids)
        power_cost = await _resolve_power_cost_per_kwh(session)
        failure_rate = await _resolve_failure_rate(session)

        return CalcContext(
            material_cost_per_gram=material_costs,
            supply_unit_cost=supply_costs,
            labor_rate_per_hour=labor_rate,
            machine_rate_per_hour=per_printer_rates,
            default_machine_rate_per_hour=default_machine_rate,
            overhead_percent=overhead,
            default_margin_percent=margin,
            printer_cost_params=printer_cost_params,
            power_cost_per_kwh=power_cost,
            failure_rate=failure_rate,
        )

    @staticmethod
    async def calculate_for_inputs(inputs: CalcInputs, *, session: AsyncSession) -> CalcResult:
        """Load context + run the pure calculator."""
        ctx = await CostEngineService.load_context(session=session, plate_inputs=inputs.plates)
        return calculate(inputs, ctx)

    @staticmethod
    async def calculate_for_job(job_id: uuid.UUID, *, session: AsyncSession) -> CalcResult:
        """Cost an existing job by its ID."""
        job = await get_job(session, job_id)  # raises JobNotFoundError on miss
        plate_inputs: list[PlateInput] = []
        for plate in job.plates:
            # Grams come back from JSON as ``{str: str}``; normalize.
            grams_map: dict[uuid.UUID, Decimal] = {}
            for k, v in (plate.print_grams_by_material or {}).items():
                grams_map[uuid.UUID(str(k))] = Decimal(str(v))
            printer_ids = [uuid.UUID(str(p)) for p in (plate.assigned_printer_ids or [])]
            plate_inputs.append(
                PlateInput(
                    parts_per_set=plate.parts_per_set,
                    print_minutes=plate.print_minutes,
                    print_grams_by_material=grams_map,
                    setup_minutes=plate.print_hours_setup_minutes,
                    assigned_printer_ids=printer_ids,
                )
            )
        inputs = CalcInputs(
            plates=plate_inputs,
            quantity_ordered=job.quantity_ordered,
        )
        return await CostEngineService.calculate_for_inputs(inputs, session=session)


__all__ = [
    "CostEngineService",
    "JobNotFoundError",
    "MissingRateConfigError",
]
