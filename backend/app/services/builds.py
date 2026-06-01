"""Build / assembly service (assembly-line epic #267, Phase 5).

A **Build** assembles N of a finished Product from its Parts + Supplies
(epic decision #2). Lifecycle: ``draft`` → ``completed`` | ``cancelled``.
Stock is only touched at completion, where the build:

* reads the product's assembly BOM (``part`` + ``supply`` lines),
* **hard-fails** if any line's on-hand at the consumption location is
  short (decision #1) — no partial consumption,
* posts ``production_consumption`` for each part/supply and a
  ``production_in`` for the product, all sharing a ``linked_build_id``,
* snapshots the build cost = sum(part cost x qty) + sum(supply per-piece
  x qty) + assembly labor (decisions #7).

Every mutation appends a typed ``production.Build*`` event inside the
caller's transaction so completion and the inventory motions succeed or
fail together.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import production as production_events
from app.models.build import Build, BuildState
from app.models.inventory_on_hand import InventoryOnHand
from app.models.part import Part
from app.models.product import Product
from app.models.product_bom_item import (
    COMPONENT_KIND_PART,
    COMPONENT_KIND_SUPPLY,
    ProductBomItem,
)
from app.models.supply import Supply
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import inventory_transactions as inventory_tx_service
from app.services.bom import _supply_cost_per_piece
from app.services.jobs import _resolve_consumption_location_id
from app.services.reference_number import ReferenceNumberService

_COST_QUANTUM = Decimal("0.000001")
_MONEY_QUANTUM = Decimal("0.01")


# ---------------------------------------------------------------------------
# Errors (routers map to HTTP)
# ---------------------------------------------------------------------------


class BuildsServiceError(Exception):
    """Base. Routers map to 400 unless a subclass overrides."""


class BuildNotFoundError(BuildsServiceError):
    """Router maps to 404."""


class InvalidBuildStateError(BuildsServiceError):
    """Router maps to 409."""


class ProductLookupError(BuildsServiceError):
    """Router maps to 400."""


class InvalidCursorError(BuildsServiceError):
    """Router maps to 400."""


class InsufficientStockError(BuildsServiceError):
    """Router maps to 409. Carries the short lines for the response."""

    def __init__(self, shortfalls: list[dict[str, str]]):
        self.shortfalls = shortfalls
        rendered = ", ".join(
            f"{s['component_kind']}:{s['component_id']} "
            f"(need {s['required']}, have {s['on_hand']})"
            for s in shortfalls
        )
        super().__init__(f"insufficient stock to build: {rendered}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode_cursor(created_at: datetime, build_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(build_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def _load_product_active(session: AsyncSession, product_id: uuid.UUID) -> Product:
    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        raise ProductLookupError(f"no product with id {product_id}")
    if product.is_archived:
        raise ProductLookupError(f"product {product_id} is archived")
    return product


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, object],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=production_events.AGGREGATE_TYPE_BUILD,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _on_hand_at(
    session: AsyncSession,
    *,
    entity_kind: str,
    entity_id: uuid.UUID,
    location_id: uuid.UUID,
) -> Decimal:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(InventoryOnHand.on_hand), 0)).where(
                InventoryOnHand.entity_kind == entity_kind,
                InventoryOnHand.entity_id == entity_id,
                InventoryOnHand.location_id == location_id,
            )
        )
    ).scalar_one()
    return total if isinstance(total, Decimal) else Decimal(str(total))


async def _labor_rate_or_none(session: AsyncSession) -> Decimal | None:
    """Resolve the cost-engine labor rate, or None if not configured.

    Lazy import to avoid importing the cost-engine service at module load.
    """
    from app.services.cost_engine.service import (
        MissingRateConfigError,
        _load_all_rates,
        _resolve_labor_rate,
    )

    try:
        rates = await _load_all_rates(session)
        return await _resolve_labor_rate(rates, session)
    except MissingRateConfigError:
        return None


@dataclass
class _PlanLine:
    component_kind: str
    component_id: uuid.UUID
    name: str
    quantity_per_product: Decimal
    required_quantity: Decimal
    on_hand: Decimal
    sufficient: bool
    unit_cost: Decimal | None
    line_cost: Decimal | None


@dataclass
class BuildPlan:
    product_id: uuid.UUID
    quantity: int
    assembly_minutes: int
    location_id: uuid.UUID | None
    lines: list[_PlanLine] = field(default_factory=list)
    component_cost: Decimal | None = None
    assembly_labor_cost: Decimal | None = None
    unit_cost: Decimal | None = None
    total_cost: Decimal | None = None
    can_build: bool = False


@dataclass
class BuildPage:
    items: list[Build]
    next_cursor: str | None


async def compute_plan(
    session: AsyncSession,
    *,
    product: Product,
    quantity: int,
    assembly_minutes: int,
    location_id: uuid.UUID | None,
) -> BuildPlan:
    """Pre-flight a build: required part/supply lines, availability, cost.

    ``location_id`` None means stock availability can't be checked yet
    (no consumption location resolved) — lines report 0 on-hand and the
    plan is not buildable.
    """
    rows = list(
        (
            await session.execute(
                select(ProductBomItem)
                .where(ProductBomItem.parent_product_id == product.id)
                .where(
                    ProductBomItem.component_kind.in_(
                        (COMPONENT_KIND_PART, COMPONENT_KIND_SUPPLY)
                    )
                )
                .order_by(ProductBomItem.created_at, ProductBomItem.id)
            )
        )
        .scalars()
        .all()
    )

    qty = Decimal(quantity)
    lines: list[_PlanLine] = []
    component_cost: Decimal | None = Decimal("0")
    all_sufficient = True

    for row in rows:
        per_product = Decimal(str(row.quantity))
        required = per_product * qty
        unit_cost: Decimal | None = None
        name = f"<missing {row.component_kind}:{row.component_id}>"

        if row.component_kind == COMPONENT_KIND_PART:
            part = (
                await session.execute(select(Part).where(Part.id == row.component_id))
            ).scalar_one_or_none()
            if part is not None:
                name = f"{part.name} ({part.sku})"
                unit_cost = (
                    Decimal(str(part.unit_cost_cached))
                    if part.unit_cost_cached is not None
                    else None
                )
        else:  # supply
            supply = (
                await session.execute(select(Supply).where(Supply.id == row.component_id))
            ).scalar_one_or_none()
            if supply is not None:
                name = supply.name
                unit_cost = _supply_cost_per_piece(supply)

        on_hand = (
            await _on_hand_at(
                session,
                entity_kind=row.component_kind,
                entity_id=row.component_id,
                location_id=location_id,
            )
            if location_id is not None
            else Decimal("0")
        )
        sufficient = location_id is not None and on_hand >= required
        if not sufficient:
            all_sufficient = False

        line_cost: Decimal | None = None
        if unit_cost is not None:
            line_cost = (unit_cost * required).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
            if component_cost is not None:
                component_cost = component_cost + line_cost
        else:
            # Unknown component cost makes the rolled-up cost unknown.
            component_cost = None

        lines.append(
            _PlanLine(
                component_kind=row.component_kind,
                component_id=row.component_id,
                name=name,
                quantity_per_product=per_product,
                required_quantity=required,
                on_hand=on_hand,
                sufficient=sufficient,
                unit_cost=unit_cost,
                line_cost=line_cost,
            )
        )

    # Assembly labor for the whole run.
    assembly_labor_cost: Decimal | None = None
    if assembly_minutes > 0:
        rate = await _labor_rate_or_none(session)
        if rate is not None:
            assembly_labor_cost = (Decimal(assembly_minutes) / Decimal(60) * rate).quantize(
                _COST_QUANTUM, rounding=ROUND_HALF_UP
            )
    else:
        assembly_labor_cost = Decimal("0")

    total_cost: Decimal | None = None
    unit_cost_out: Decimal | None = None
    if component_cost is not None and assembly_labor_cost is not None:
        total_cost = (component_cost + assembly_labor_cost).quantize(
            _MONEY_QUANTUM, rounding=ROUND_HALF_UP
        )
        unit_cost_out = (total_cost / qty).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    return BuildPlan(
        product_id=product.id,
        quantity=quantity,
        assembly_minutes=assembly_minutes,
        location_id=location_id,
        lines=lines,
        component_cost=(
            component_cost.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            if component_cost is not None
            else None
        ),
        assembly_labor_cost=(
            assembly_labor_cost.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            if assembly_labor_cost is not None
            else None
        ),
        unit_cost=unit_cost_out,
        total_cost=total_cost,
        can_build=bool(lines) and all_sufficient,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    quantity: int,
    assembly_minutes: int | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> Build:
    if quantity <= 0:
        raise BuildsServiceError("quantity must be > 0")
    product = await _load_product_active(session, product_id)

    # Default the labor to the product's configured per-unit assembly time
    # scaled by the build quantity; the caller may override.
    if assembly_minutes is None:
        assembly_minutes = (product.assembly_minutes or 0) * quantity
    if assembly_minutes < 0:
        raise BuildsServiceError("assembly_minutes must be >= 0")

    build_number = await ReferenceNumberService.allocate("BUILD", session=session)
    build = Build(
        build_number=build_number,
        product_id=product_id,
        state=BuildState.DRAFT,
        quantity=quantity,
        assembly_minutes=assembly_minutes,
        notes=notes,
        actor_user_id=actor_user_id,
    )
    session.add(build)
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_BUILD_CREATED,
        aggregate_id=build.id,
        payload={
            "build_id": str(build.id),
            "build_number": build.build_number,
            "product_id": str(build.product_id),
            "quantity": build.quantity,
            "assembly_minutes": build.assembly_minutes,
        },
        actor_user_id=actor_user_id,
    )
    return build


async def get(session: AsyncSession, build_id: uuid.UUID) -> Build:
    row = (
        await session.execute(select(Build).where(Build.id == build_id))
    ).scalar_one_or_none()
    if row is None:
        raise BuildNotFoundError(str(build_id))
    return row


_EDITABLE_FIELDS = ("quantity", "assembly_minutes", "notes")


async def update(
    session: AsyncSession,
    *,
    build_id: uuid.UUID,
    patch: dict[str, object],
    actor_user_id: uuid.UUID | None,
) -> Build:
    build = await get(session, build_id)
    if build.state is not BuildState.DRAFT:
        raise InvalidBuildStateError(
            f"cannot edit a build in state {build.state.value!r}; only drafts are editable"
        )
    if "quantity" in patch:
        qty = patch["quantity"]
        if not isinstance(qty, int) or qty <= 0:
            raise BuildsServiceError("quantity must be > 0")
    if "assembly_minutes" in patch:
        am = patch["assembly_minutes"]
        if not isinstance(am, int) or am < 0:
            raise BuildsServiceError("assembly_minutes must be >= 0")
    changed = False
    for f in _EDITABLE_FIELDS:
        if f in patch:
            setattr(build, f, patch[f])
            changed = True
    if changed:
        await session.flush()
    return build


async def complete(
    session: AsyncSession,
    *,
    build_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Build:
    """Consume parts + supplies and credit product on-hand.

    Hard-fails (no writes) if any required line is short. All inventory
    motions share ``linked_build_id = build.id``.
    """
    build = await get(session, build_id)
    if build.state is not BuildState.DRAFT:
        raise InvalidBuildStateError(f"cannot complete a build in state {build.state.value!r}")
    product = await _load_product_active(session, build.product_id)

    location_id = await _resolve_consumption_location_id(session)
    plan = await compute_plan(
        session,
        product=product,
        quantity=build.quantity,
        assembly_minutes=build.assembly_minutes,
        location_id=location_id,
    )

    shortfalls = [
        {
            "component_kind": line.component_kind,
            "component_id": str(line.component_id),
            "required": str(line.required_quantity),
            "on_hand": str(line.on_hand),
        }
        for line in plan.lines
        if not line.sufficient
    ]
    if shortfalls:
        raise InsufficientStockError(shortfalls)

    # Lazy import to avoid pulling the COGS service (and its sales deps)
    # into the builds module at load time.
    from app.services.cogs import service as cogs_service

    consumed: list[dict[str, str]] = []
    # Actual component cost of this run. Parts are valued at their real
    # FIFO ledger lot cost (epic #267 Phase 6a); supplies at per-piece.
    component_total = Decimal("0")
    for line in plan.lines:
        if line.component_kind == COMPONENT_KIND_PART:
            # FIFO cost basis for the part, location-scoped. NULL lot
            # costs fall back to the part's cached cost (decision #3).
            fifo_total = await cogs_service.cost_consumption(
                session,
                entity_kind=COMPONENT_KIND_PART,
                entity_id=line.component_id,
                quantity=line.required_quantity,
                location_id=location_id,
                fallback_unit_cost=line.unit_cost,
            )
            eff_unit = (
                (fifo_total / line.required_quantity).quantize(
                    _COST_QUANTUM, rounding=ROUND_HALF_UP
                )
                if line.required_quantity > 0
                else Decimal("0")
            )
            line_total = fifo_total
            consume_unit_cost: Decimal | None = eff_unit
        else:
            # Supplies: per-piece cached cost (Phase 6a scopes FIFO to
            # parts; supplies keep the existing per-piece basis).
            consume_unit_cost = line.unit_cost
            line_total = (
                line.line_cost
                if line.line_cost is not None
                else Decimal("0")
            )

        await inventory_tx_service.record(
            session,
            kind="production_consumption",
            entity_kind=line.component_kind,
            entity_id=line.component_id,
            location_id=location_id,
            quantity=line.required_quantity,
            actor_user_id=actor_user_id,
            unit_cost=consume_unit_cost,
            linked_build_id=build.id,
            reason=f"build {build.build_number} consumed",
        )
        component_total = component_total + line_total
        consumed.append(
            {
                "entity_kind": line.component_kind,
                "entity_id": str(line.component_id),
                "quantity": str(line.required_quantity),
            }
        )

    # Roll the actuals up: components (parts at FIFO + supplies) + the
    # build's assembly labor → product unit cost.
    assembly_labor = plan.assembly_labor_cost or Decimal("0")
    total_cost = (component_total + assembly_labor).quantize(
        _MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    unit_cost = (
        (total_cost / Decimal(build.quantity)).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if build.quantity > 0
        else Decimal("0")
    )

    # Credit the finished product at the true consumed cost.
    await inventory_tx_service.record(
        session,
        kind="production_in",
        entity_kind="product",
        entity_id=product.id,
        location_id=location_id,
        quantity=Decimal(build.quantity),
        actor_user_id=actor_user_id,
        unit_cost=unit_cost,
        linked_build_id=build.id,
        reason=f"build {build.build_number} completed",
    )

    build.state = BuildState.COMPLETED
    build.location_id = location_id
    build.unit_cost_cached = unit_cost
    build.total_cost_cached = total_cost
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_BUILD_COMPLETED,
        aggregate_id=build.id,
        payload={
            "build_id": str(build.id),
            "product_id": str(product.id),
            "quantity": build.quantity,
            "location_id": str(location_id),
            "unit_cost": str(unit_cost),
            "total_cost": str(total_cost),
            "consumed": consumed,
        },
        actor_user_id=actor_user_id,
    )
    return build


async def cancel(
    session: AsyncSession,
    *,
    build_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Build:
    build = await get(session, build_id)
    if build.state is not BuildState.DRAFT:
        raise InvalidBuildStateError(f"cannot cancel a build in state {build.state.value!r}")
    build.state = BuildState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=production_events.TYPE_BUILD_CANCELLED,
        aggregate_id=build.id,
        payload={"build_id": str(build.id)},
        actor_user_id=actor_user_id,
    )
    return build


async def list_builds(
    session: AsyncSession,
    *,
    state: str | None = None,
    product_id: uuid.UUID | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> BuildPage:
    stmt = select(Build)
    if state is not None:
        try:
            stmt = stmt.where(Build.state == BuildState(state))
        except ValueError as exc:
            raise BuildsServiceError(f"invalid state filter: {state!r}") from exc
    if product_id is not None:
        stmt = stmt.where(Build.product_id == product_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Build.build_number.ilike(like))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Build.created_at < anchor_ts,
                and_(Build.created_at == anchor_ts, Build.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Build.created_at), desc(Build.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return BuildPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "BuildNotFoundError",
    "BuildPage",
    "BuildPlan",
    "BuildsServiceError",
    "InsufficientStockError",
    "InvalidBuildStateError",
    "InvalidCursorError",
    "ProductLookupError",
    "cancel",
    "compute_plan",
    "create",
    "complete",
    "get",
    "list_builds",
    "update",
]
