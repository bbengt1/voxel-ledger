"""BOM service (Phase 2.4).

Polymorphic bill-of-materials with cycle detection, depth limit, and a
cost-rollup that walks the tree.

Every mutation appends a typed ``catalog.Bom*`` event via
``EventStore.append`` inside the same transaction as the row write so
the wildcard audit-log projection picks it up.

Cycle detection
---------------
When a sub-product is added to a BOM, we BFS the candidate child's
transitive BOM tree. If the new parent is found anywhere downstream,
the insert is rejected with :class:`BomCycleError` (the router maps
this to HTTP 400). A depth guard of 50 levels stops runaway walks.

Postgres can do this in one round-trip via a recursive CTE; SQLite
falls back to a Python loop. Both paths are kept behaviorally identical.

Cost rollup
-----------
:func:`compute_cost_tree` is the canonical helper. It walks the BOM
recursively and returns NULL on any leg with an unknown component cost
or where depth exceeds ``max_depth``. The Phase 2.4
``product_cost`` projection calls this helper to recompute
``product.unit_cost_cached``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import catalog as catalog_events
from app.models.material import Material
from app.models.part import Part
from app.models.product import Product
from app.models.product_bom_item import (
    COMPONENT_KIND_MATERIAL,
    COMPONENT_KIND_PART,
    COMPONENT_KIND_PRODUCT,
    COMPONENT_KIND_SUPPLY,
    COMPONENT_KIND_VALUES,
    ProductBomItem,
)
from app.models.supply import Supply
from app.schemas.events import EventCreate
from app.services import event_store

DEFAULT_MAX_DEPTH: int = 50

_COST_QUANTUM = Decimal("0.000001")


class BomServiceError(Exception):
    """Base. Routers map to 400 unless a subclass overrides."""


class BomItemNotFoundError(BomServiceError):
    """Router maps to 404."""


class ProductNotFoundError(BomServiceError):
    """Router maps to 404."""


class ComponentNotFoundError(BomServiceError):
    """Router maps to 404."""


class ArchivedTargetError(BomServiceError):
    """Parent or component is archived."""


class InvalidComponentKindError(BomServiceError):
    pass


class InvalidQuantityError(BomServiceError):
    pass


class BomCycleError(BomServiceError):
    """Adding the component would introduce a BOM cycle."""

    def __init__(self, parent_id: uuid.UUID, component_id: uuid.UUID, path: list[uuid.UUID]):
        self.parent_id = parent_id
        self.component_id = component_id
        self.path = path
        rendered = " -> ".join(str(p) for p in path)
        super().__init__(
            f"BOM cycle detected: adding product {component_id} to {parent_id} would "
            f"create cycle ({rendered})"
        )


class BomDepthLimitError(BomServiceError):
    """Walking the candidate's tree exceeded the depth limit."""

    def __init__(self, max_depth: int):
        self.max_depth = max_depth
        super().__init__(
            f"BOM depth limit exceeded (max {max_depth}); refusing to add component "
            "to avoid a runaway tree"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dec_to_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _supply_cost_per_piece(supply: Supply) -> Decimal:
    """Cost of a single *piece* of a supply.

    A supply's ``unit_cost`` is the price of one purchasable *unit* (e.g.
    a box). ``pieces_per_unit`` says how many usable pieces that unit
    holds (e.g. 100 screws per box). BOM quantities are expressed in
    pieces, so cost-per-piece is ``unit_cost / pieces_per_unit``. When
    ``pieces_per_unit`` is unset or non-positive we treat one unit as one
    piece (matches the UI's documented "1 unit = 1 piece" fallback).
    """
    unit_cost = _as_decimal(supply.unit_cost)
    ppu = supply.pieces_per_unit
    if ppu and ppu > 0:
        return (unit_cost / Decimal(ppu)).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
    return unit_cost


async def _assembly_labor_cost(session: AsyncSession, product: Product) -> Decimal | None:
    """Labor to assemble one finished product = ``assembly_minutes/60 x
    labor_rate`` (epic #267 Phase 3, decision #1). Returns ``None`` when the
    labor rate isn't configured (so the product cost reads as unknown, like
    any missing component cost).
    """
    minutes = product.assembly_minutes or 0
    if minutes <= 0:
        return Decimal("0")
    # Lazy import: the cost-engine service imports this module, so importing
    # it at module load would cycle.
    from app.services.cost_engine.service import (
        MissingRateConfigError,
        _load_all_rates,
        _resolve_labor_rate,
    )

    try:
        rates = await _load_all_rates(session)
        labor_rate = await _resolve_labor_rate(rates, session)
    except MissingRateConfigError:
        return None
    return (Decimal(minutes) / Decimal(60) * labor_rate).quantize(
        _COST_QUANTUM, rounding=ROUND_HALF_UP
    )


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=catalog_events.PRODUCT_AGGREGATE_TYPE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _load_parent(session: AsyncSession, parent_product_id: uuid.UUID) -> Product:
    row = (
        await session.execute(select(Product).where(Product.id == parent_product_id))
    ).scalar_one_or_none()
    if row is None:
        raise ProductNotFoundError(str(parent_product_id))
    if row.is_archived:
        raise ArchivedTargetError(f"parent product {parent_product_id} is archived")
    return row


async def _load_component(
    session: AsyncSession,
    *,
    component_kind: str,
    component_id: uuid.UUID,
) -> tuple[str, Decimal | None, bool]:
    """Return ``(resolved_name, unit_cost_or_None, is_archived)``."""
    if component_kind == COMPONENT_KIND_MATERIAL:
        row = (
            await session.execute(select(Material).where(Material.id == component_id))
        ).scalar_one_or_none()
        if row is None:
            raise ComponentNotFoundError(f"material {component_id} not found")
        return row.name, _as_decimal(row.current_cost_per_gram), bool(row.is_archived)
    if component_kind == COMPONENT_KIND_SUPPLY:
        row = (
            await session.execute(select(Supply).where(Supply.id == component_id))
        ).scalar_one_or_none()
        if row is None:
            raise ComponentNotFoundError(f"supply {component_id} not found")
        return row.name, _supply_cost_per_piece(row), bool(row.is_archived)
    if component_kind == COMPONENT_KIND_PART:
        row = (
            await session.execute(select(Part).where(Part.id == component_id))
        ).scalar_one_or_none()
        if row is None:
            raise ComponentNotFoundError(f"part {component_id} not found")
        # Part cost is its cached unit cost (materials + print/labor/machine
        # + overhead), maintained by the part_cost projection. None when the
        # part isn't priceable yet (no rate config) → propagates as unknown.
        unit_cost = None if row.unit_cost_cached is None else _as_decimal(row.unit_cost_cached)
        return row.name, unit_cost, bool(row.is_archived)
    if component_kind == COMPONENT_KIND_PRODUCT:
        row = (
            await session.execute(select(Product).where(Product.id == component_id))
        ).scalar_one_or_none()
        if row is None:
            raise ComponentNotFoundError(f"product {component_id} not found")
        unit_cost = None if row.unit_cost_cached is None else _as_decimal(row.unit_cost_cached)
        return row.name, unit_cost, bool(row.is_archived)
    raise InvalidComponentKindError(
        f"component_kind must be one of {COMPONENT_KIND_VALUES}, got {component_kind!r}"
    )


# ---------------------------------------------------------------------------
# Cycle / ancestor walks
# ---------------------------------------------------------------------------


async def _walks_back_to(
    target_product_id: uuid.UUID,
    starting_from_product_id: uuid.UUID,
    *,
    session: AsyncSession,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> tuple[bool, list[uuid.UUID]]:
    """BFS descendants of ``starting_from_product_id`` looking for ``target``.

    Returns ``(found, path)``. ``path`` is the chain from
    ``starting_from_product_id`` down to ``target_product_id`` when
    found; empty list otherwise.

    Raises :class:`BomDepthLimitError` if depth exceeds ``max_depth``.

    Postgres branch: a single recursive CTE collects the whole descendant
    set; we then walk a Python adjacency map to recover the path so the
    error message can name the offending chain. SQLite branch: pure
    Python BFS.

    A visited set guards against legitimate diamond-shaped overlap
    (same sub-product used in two branches is fine — not a cycle).
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""

    # Build adjacency: parent_id -> [child_product_id, ...] for the whole
    # descendant set of the starting node.
    adjacency: dict[uuid.UUID, list[uuid.UUID]] = {}

    if dialect == "postgresql":
        cte_sql = text(
            """
            WITH RECURSIVE descendants AS (
                SELECT parent_product_id, component_id
                FROM product_bom_item
                WHERE component_kind = 'product'
                  AND parent_product_id = :start
                UNION
                SELECT pb.parent_product_id, pb.component_id
                FROM product_bom_item pb
                JOIN descendants d ON pb.parent_product_id = d.component_id
                WHERE pb.component_kind = 'product'
            )
            SELECT parent_product_id, component_id FROM descendants
            """
        )
        result = await session.execute(cte_sql, {"start": starting_from_product_id})
        for parent, child in result.all():
            adjacency.setdefault(parent, []).append(child)
    else:
        # SQLite branch: iterative BFS to assemble the descendant set.
        frontier: list[uuid.UUID] = [starting_from_product_id]
        seen: set[uuid.UUID] = set()
        depth = 0
        while frontier:
            depth += 1
            if depth > max_depth:
                raise BomDepthLimitError(max_depth)
            next_frontier: list[uuid.UUID] = []
            stmt = (
                select(ProductBomItem.parent_product_id, ProductBomItem.component_id)
                .where(ProductBomItem.component_kind == COMPONENT_KIND_PRODUCT)
                .where(ProductBomItem.parent_product_id.in_(frontier))
            )
            rows = (await session.execute(stmt)).all()
            for parent, child in rows:
                adjacency.setdefault(parent, []).append(child)
                if child not in seen:
                    seen.add(child)
                    next_frontier.append(child)
            frontier = next_frontier

    # Now BFS from ``starting_from_product_id`` over ``adjacency`` and
    # track parents so we can reconstruct the path if we find ``target``.
    parents: dict[uuid.UUID, uuid.UUID] = {}
    queue: list[tuple[uuid.UUID, int]] = [(starting_from_product_id, 0)]
    visited: set[uuid.UUID] = {starting_from_product_id}
    while queue:
        node, depth = queue.pop(0)
        if depth > max_depth:
            raise BomDepthLimitError(max_depth)
        for child in adjacency.get(node, ()):
            if child == target_product_id:
                # Found it — reconstruct path.
                path = [child, node]
                cursor = node
                while cursor in parents:
                    cursor = parents[cursor]
                    path.append(cursor)
                path.reverse()
                return True, path
            if child not in visited:
                visited.add(child)
                parents[child] = node
                queue.append((child, depth + 1))

    return False, []


async def _ancestors_of(
    product_id: uuid.UUID,
    *,
    session: AsyncSession,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> set[uuid.UUID]:
    """Return every product that contains ``product_id`` transitively in its BOM.

    Does NOT include ``product_id`` itself; callers can union it in if
    they want the changed product plus ancestors.
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        cte_sql = text(
            """
            WITH RECURSIVE ancestors AS (
                SELECT parent_product_id FROM product_bom_item
                WHERE component_kind = 'product' AND component_id = :start
                UNION
                SELECT pb.parent_product_id FROM product_bom_item pb
                JOIN ancestors a ON pb.component_id = a.parent_product_id
                WHERE pb.component_kind = 'product'
            )
            SELECT parent_product_id FROM ancestors
            """
        )
        rows = (await session.execute(cte_sql, {"start": product_id})).all()
        return {r[0] for r in rows}

    # SQLite branch: iterative BFS.
    result: set[uuid.UUID] = set()
    frontier: list[uuid.UUID] = [product_id]
    depth = 0
    while frontier:
        depth += 1
        if depth > max_depth:
            # In ancestor-walk land, treat overflow as "stop" rather than
            # erroring — the projection should still make progress.
            break
        stmt = (
            select(ProductBomItem.parent_product_id)
            .where(ProductBomItem.component_kind == COMPONENT_KIND_PRODUCT)
            .where(ProductBomItem.component_id.in_(frontier))
            .distinct()
        )
        rows = (await session.execute(stmt)).all()
        next_frontier: list[uuid.UUID] = []
        for (parent,) in rows:
            if parent not in result:
                result.add(parent)
                next_frontier.append(parent)
        frontier = next_frontier
    return result


async def _products_containing_component(
    component_kind: str,
    component_id: uuid.UUID,
    *,
    session: AsyncSession,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> set[uuid.UUID]:
    """Find products whose BOM tree directly contains a (kind, id) component,
    then expand transitively through product ancestors."""
    stmt = (
        select(ProductBomItem.parent_product_id)
        .where(ProductBomItem.component_kind == component_kind)
        .where(ProductBomItem.component_id == component_id)
        .distinct()
    )
    rows = (await session.execute(stmt)).all()
    direct: set[uuid.UUID] = {r[0] for r in rows}
    affected: set[uuid.UUID] = set(direct)
    for pid in direct:
        affected.update(await _ancestors_of(pid, session=session, max_depth=max_depth))
    return affected


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def add_component(
    session: AsyncSession,
    *,
    parent_product_id: uuid.UUID,
    component_kind: str,
    component_id: uuid.UUID,
    quantity: Decimal,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> ProductBomItem:
    # Products are assembled from parts + supplies (epic #267 decision #3).
    # Legacy ``material`` / ``product`` kinds remain valid in the enum + cost
    # rollup for pre-migration rows, but are rejected on new BOM lines.
    if component_kind not in (COMPONENT_KIND_PART, COMPONENT_KIND_SUPPLY):
        raise InvalidComponentKindError(
            f"product BOM components must be one of "
            f"{(COMPONENT_KIND_PART, COMPONENT_KIND_SUPPLY)}; got {component_kind!r}"
        )
    quantity = _as_decimal(quantity)
    if quantity <= 0:
        raise InvalidQuantityError("quantity must be > 0")

    await _load_parent(session, parent_product_id)

    if component_kind == COMPONENT_KIND_PRODUCT and component_id == parent_product_id:
        raise BomCycleError(parent_product_id, component_id, [parent_product_id])

    _, _unit_cost, is_archived = await _load_component(
        session, component_kind=component_kind, component_id=component_id
    )
    if is_archived:
        raise ArchivedTargetError(f"component {component_kind}:{component_id} is archived")

    if component_kind == COMPONENT_KIND_PRODUCT:
        found, path = await _walks_back_to(parent_product_id, component_id, session=session)
        if found:
            raise BomCycleError(parent_product_id, component_id, path)

    item = ProductBomItem(
        parent_product_id=parent_product_id,
        component_kind=component_kind,
        component_id=component_id,
        quantity=quantity,
        notes=notes,
    )
    session.add(item)
    await session.flush()

    await _emit(
        session,
        event_type=catalog_events.TYPE_BOM_COMPONENT_ADDED,
        aggregate_id=parent_product_id,
        payload={
            "bom_item_id": str(item.id),
            "parent_product_id": str(parent_product_id),
            "component_kind": component_kind,
            "component_id": str(component_id),
            "quantity": str(quantity),
        },
        actor_user_id=actor_user_id,
    )
    return item


async def get_item(session: AsyncSession, bom_item_id: uuid.UUID) -> ProductBomItem:
    row = (
        await session.execute(select(ProductBomItem).where(ProductBomItem.id == bom_item_id))
    ).scalar_one_or_none()
    if row is None:
        raise BomItemNotFoundError(str(bom_item_id))
    return row


async def remove_component(
    session: AsyncSession,
    *,
    bom_item_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    item = await get_item(session, bom_item_id)
    parent_product_id = item.parent_product_id
    component_kind = item.component_kind
    component_id = item.component_id
    await session.delete(item)
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_BOM_COMPONENT_REMOVED,
        aggregate_id=parent_product_id,
        payload={
            "bom_item_id": str(bom_item_id),
            "parent_product_id": str(parent_product_id),
            "component_kind": component_kind,
            "component_id": str(component_id),
        },
        actor_user_id=actor_user_id,
    )


async def update_component_quantity(
    session: AsyncSession,
    *,
    bom_item_id: uuid.UUID,
    new_quantity: Decimal,
    actor_user_id: uuid.UUID | None,
) -> ProductBomItem:
    new_quantity = _as_decimal(new_quantity)
    if new_quantity <= 0:
        raise InvalidQuantityError("quantity must be > 0")
    item = await get_item(session, bom_item_id)
    old_quantity = _as_decimal(item.quantity)
    if old_quantity == new_quantity:
        return item
    item.quantity = new_quantity
    await session.flush()
    await _emit(
        session,
        event_type=catalog_events.TYPE_BOM_COMPONENT_QUANTITY_CHANGED,
        aggregate_id=item.parent_product_id,
        payload={
            "bom_item_id": str(item.id),
            "parent_product_id": str(item.parent_product_id),
            "old_quantity": str(old_quantity),
            "new_quantity": str(new_quantity),
        },
        actor_user_id=actor_user_id,
    )
    return item


# ---------------------------------------------------------------------------
# Read: flat BOM + cost tree
# ---------------------------------------------------------------------------


@dataclass
class ResolvedBomItem:
    item: ProductBomItem
    resolved_name: str
    resolved_unit_cost: Decimal | None
    line_cost: Decimal | None


async def get_bom(session: AsyncSession, *, product_id: uuid.UUID) -> list[ResolvedBomItem]:
    """Flat BOM for a product, joined to the resolved entity."""
    rows = list(
        (
            await session.execute(
                select(ProductBomItem)
                .where(ProductBomItem.parent_product_id == product_id)
                .order_by(ProductBomItem.created_at, ProductBomItem.id)
            )
        )
        .scalars()
        .all()
    )

    out: list[ResolvedBomItem] = []
    for row in rows:
        try:
            name, unit_cost, _archived = await _load_component(
                session,
                component_kind=row.component_kind,
                component_id=row.component_id,
            )
        except ComponentNotFoundError:
            # Component vanished out from under us (polymorphic, no FK).
            # Render as unknown rather than 500ing the list.
            name = f"<missing {row.component_kind}:{row.component_id}>"
            unit_cost = None
        line_cost: Decimal | None = None
        if unit_cost is not None:
            line_cost = (_as_decimal(row.quantity) * unit_cost).quantize(
                _COST_QUANTUM, rounding=ROUND_HALF_UP
            )
        out.append(
            ResolvedBomItem(
                item=row,
                resolved_name=name,
                resolved_unit_cost=unit_cost,
                line_cost=line_cost,
            )
        )
    return out


@dataclass
class CostTreeNode:
    product_id: uuid.UUID
    resolved_name: str
    total_cost: Decimal | None
    truncated_at_depth: bool = False
    components: list[CostTreeComponent] = field(default_factory=list)


@dataclass
class CostTreeComponent:
    bom_item_id: uuid.UUID
    component_kind: str
    component_id: uuid.UUID
    resolved_name: str
    quantity: Decimal
    unit_cost: Decimal | None
    line_cost: Decimal | None
    sub_tree: CostTreeNode | None = None


async def compute_cost_tree(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    max_depth: int = DEFAULT_MAX_DEPTH,
    _depth: int = 0,
    _seen: set[uuid.UUID] | None = None,
) -> CostTreeNode:
    """Recursive cost tree for a product.

    ``total_cost`` is None on any leg with an unknown component cost or
    when depth exceeds ``max_depth``. ``_seen`` is a defense-in-depth
    guard against cycles that somehow slipped past the add-time check
    (it shouldn't ever fire in practice).
    """
    seen = _seen if _seen is not None else set()

    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError(str(product_id))

    node = CostTreeNode(
        product_id=product_id,
        resolved_name=product.name,
        total_cost=Decimal("0"),
    )

    if _depth >= max_depth:
        node.truncated_at_depth = True
        node.total_cost = None
        return node

    if product_id in seen:
        # Cycle escape hatch.
        node.truncated_at_depth = True
        node.total_cost = None
        return node
    seen = seen | {product_id}

    rows = list(
        (
            await session.execute(
                select(ProductBomItem)
                .where(ProductBomItem.parent_product_id == product_id)
                .order_by(ProductBomItem.created_at, ProductBomItem.id)
            )
        )
        .scalars()
        .all()
    )

    running: Decimal | None = Decimal("0")
    for row in rows:
        try:
            name, unit_cost, _archived = await _load_component(
                session,
                component_kind=row.component_kind,
                component_id=row.component_id,
            )
        except ComponentNotFoundError:
            name = f"<missing {row.component_kind}:{row.component_id}>"
            unit_cost = None

        quantity = _as_decimal(row.quantity)
        sub_tree: CostTreeNode | None = None

        if row.component_kind == COMPONENT_KIND_PRODUCT:
            sub_tree = await compute_cost_tree(
                session,
                product_id=row.component_id,
                max_depth=max_depth,
                _depth=_depth + 1,
                _seen=seen,
            )
            # For sub-products, prefer the freshly-walked total_cost over
            # the cached column so the projection can recompute without
            # depending on its own write order.
            unit_cost = sub_tree.total_cost

        line_cost: Decimal | None = None
        if unit_cost is not None:
            line_cost = (quantity * unit_cost).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)

        if line_cost is None:
            running = None
        elif running is not None:
            running = running + line_cost

        node.components.append(
            CostTreeComponent(
                bom_item_id=row.id,
                component_kind=row.component_kind,
                component_id=row.component_id,
                resolved_name=name,
                quantity=quantity,
                unit_cost=unit_cost,
                line_cost=line_cost,
                sub_tree=sub_tree,
            )
        )

    # Assembly labor (epic #267 Phase 3): plain sum on top of component
    # costs — parts already carry their own overhead (decision #2). Unknown
    # labor rate makes the whole product cost unknown.
    if running is not None:
        labor = await _assembly_labor_cost(session, product)
        running = None if labor is None else running + labor

    if running is not None:
        running = running.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
    node.total_cost = running
    return node


async def supply_line_costs_per_piece(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
) -> dict[uuid.UUID, Decimal]:
    """Per-finished-piece supply cost from a product's *direct* BOM.

    Returns ``{supply_id: quantity * cost_per_piece}`` for every direct
    ``supply`` component of ``product_id`` — the non-printed parts (screws,
    magnets, inserts, packaging) added on top of the printed plates. Used
    by the cost engine to populate ``CalcContext.supply_unit_cost``.

    Scope (v1): only the product's own direct supply items. Materials in a
    BOM are skipped — filament is costed from plates, and a BOM material
    would double-count. Sub-product (assembly) supplies are not flattened
    here; nested rollups remain :func:`compute_cost_tree`'s job. Archived
    supplies are still included — pricing an existing job shouldn't depend
    on whether a part was later archived.
    """
    rows = list(
        (
            await session.execute(
                select(ProductBomItem)
                .where(
                    ProductBomItem.parent_product_id == product_id,
                    ProductBomItem.component_kind == COMPONENT_KIND_SUPPLY,
                )
                .order_by(ProductBomItem.created_at, ProductBomItem.id)
            )
        )
        .scalars()
        .all()
    )

    line_costs: dict[uuid.UUID, Decimal] = {}
    for row in rows:
        supply = (
            await session.execute(select(Supply).where(Supply.id == row.component_id))
        ).scalar_one_or_none()
        if supply is None:
            # A dangling reference shouldn't sink the whole calc; treat as
            # zero (mirrors the cost engine's missing-material handling).
            continue
        per_piece = _supply_cost_per_piece(supply)
        line = (_as_decimal(row.quantity) * per_piece).quantize(
            _COST_QUANTUM, rounding=ROUND_HALF_UP
        )
        # A supply can legitimately appear on multiple BOM lines; sum them.
        line_costs[row.component_id] = line_costs.get(row.component_id, Decimal("0")) + line
    return line_costs


async def material_rollup_for_product(
    session: AsyncSession, *, product_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    """Derived material usage to build one finished product (epic #267 Phase 3).

    Walks the product's direct ``part`` BOM components. A part prints
    ``print_grams_by_material`` grams per run producing ``parts_per_run``
    pieces, so one part uses ``grams / parts_per_run`` of each material; a
    product needing ``quantity`` of that part uses
    ``quantity * grams / parts_per_run``. Returns ``{material_id: grams}``
    aggregated across all parts (read-only; for reporting / where-used).
    """
    rows = list(
        (
            await session.execute(
                select(ProductBomItem).where(
                    ProductBomItem.parent_product_id == product_id,
                    ProductBomItem.component_kind == COMPONENT_KIND_PART,
                )
            )
        )
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, Decimal] = {}
    for row in rows:
        part = (
            await session.execute(select(Part).where(Part.id == row.component_id))
        ).scalar_one_or_none()
        if part is None:
            continue
        ppr = Decimal(part.parts_per_run or 1)
        qty = _as_decimal(row.quantity)
        for mat_id_str, grams_str in (part.print_grams_by_material or {}).items():
            try:
                mid = uuid.UUID(str(mat_id_str))
            except ValueError:
                continue
            per_product = qty * _as_decimal(grams_str) / ppr
            out[mid] = out.get(mid, Decimal("0")) + per_product
    return {mid: g.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP) for mid, g in out.items()}


__all__ = [
    "DEFAULT_MAX_DEPTH",
    "ArchivedTargetError",
    "BomCycleError",
    "BomDepthLimitError",
    "BomItemNotFoundError",
    "BomServiceError",
    "ComponentNotFoundError",
    "CostTreeComponent",
    "CostTreeNode",
    "InvalidComponentKindError",
    "InvalidQuantityError",
    "ProductNotFoundError",
    "ResolvedBomItem",
    "_ancestors_of",
    "_products_containing_component",
    "_walks_back_to",
    "add_component",
    "compute_cost_tree",
    "get_bom",
    "get_item",
    "material_rollup_for_product",
    "remove_component",
    "supply_line_costs_per_piece",
    "update_component_quantity",
]
