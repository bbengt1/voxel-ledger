"""Replay parity for the product_cost projection.

The Phase 2.4 cost rollup must be reproducible from the BOM tables +
material/supply leaf state alone. This test:

1. Builds a multi-level BOM with materials, supplies, and sub-products.
2. Snapshots every ``product.unit_cost_cached``.
3. Wipes ``unit_cost_cached`` to NULL on every row.
4. Recomputes by walking ``compute_cost_tree`` for each product (in
   leaf-first order so sub-products converge first).
5. Asserts the resulting values match the original snapshot exactly.

This is the load-bearing guarantee the Phase 5 cost engine depends on:
``unit_cost_cached`` can always be rebuilt from current BOM topology
plus leaf-level cached costs (which themselves derive from the
``inventory.MaterialReceived`` event stream and supply unit_cost).

Note on the projection-as-replayer path
---------------------------------------
The replay engine in ``app.projections.replay`` is designed for
projections whose handlers do not emit new events. The product_cost
projection intentionally DOES emit ``ProductCostChanged`` to propagate
up the tree on live appends; replaying those handlers through
``replay_handler`` would re-append events into the log. The parity
invariant we actually care about — "the read model can be rebuilt from
the source data" — is what this test verifies, without running the
handlers' recursive emission path.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models import Base
from app.models.product import Product
from app.models.product_bom_item import COMPONENT_KIND_PRODUCT, ProductBomItem
from app.services import bom as bom_service
from app.services import inventory_locations as locations_service
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services import products as products_service
from app.services import supplies as supplies_service
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.asyncio
async def test_bom_replay_parity(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as s:
        # Phase 3.2: receipts need a fallback receiving location.
        await locations_service.create(
            s, name="Receiving", code="RX", kind="workshop", actor_user_id=None
        )
        m = await materials_service.create(
            s,
            name="M",
            brand="X",
            material_type="PLA",
            color=None,
            density_g_per_cm3=None,
            actor_user_id=None,
        )
        await receipts_service.record(
            s,
            material_id=m.id,
            grams=Decimal("1000"),
            total_cost=Decimal("15000"),
            actor_user_id=None,
        )
        sup = await supplies_service.create(
            s,
            name="bag",
            unit="ea",
            unit_cost=Decimal("0.25"),
            vendor=None,
            on_hand=Decimal("0"),
            actor_user_id=None,
        )
        p_leaf = await products_service.create(
            s,
            name="leaf",
            description=None,
            unit_price=Decimal("10"),
            actor_user_id=None,
        )
        p_mid = await products_service.create(
            s,
            name="mid",
            description=None,
            unit_price=Decimal("20"),
            actor_user_id=None,
        )
        p_top = await products_service.create(
            s,
            name="top",
            description=None,
            unit_price=Decimal("30"),
            actor_user_id=None,
        )
        await s.commit()

    # Build: leaf = 50g M + 4 bag; mid = 1 leaf + 25g M; top = 2 mid + 1 bag.
    async with factory() as s:
        await bom_service.add_component(
            s,
            parent_product_id=p_leaf.id,
            component_kind="material",
            component_id=m.id,
            quantity=Decimal("50"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p_leaf.id,
            component_kind="supply",
            component_id=sup.id,
            quantity=Decimal("4"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p_mid.id,
            component_kind="product",
            component_id=p_leaf.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p_mid.id,
            component_kind="material",
            component_id=m.id,
            quantity=Decimal("25"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p_top.id,
            component_kind="product",
            component_id=p_mid.id,
            quantity=Decimal("2"),
            actor_user_id=None,
        )
        await bom_service.add_component(
            s,
            parent_product_id=p_top.id,
            component_kind="supply",
            component_id=sup.id,
            quantity=Decimal("1"),
            actor_user_id=None,
        )
        await s.commit()

    async with factory() as s:
        rows = (await s.execute(select(Product).order_by(Product.id))).scalars().all()
        before = {r.id: r.unit_cost_cached for r in rows}
    assert all(v is not None for v in before.values())

    # Wipe the cached column on every product.
    async with factory() as s:
        await s.execute(update(Product).values(unit_cost_cached=None))
        await s.commit()

    # Rebuild: process products in leaf-first order so sub-product costs
    # are settled before parents read them.
    async with factory() as s:
        adjacency_rows = (
            await s.execute(
                select(ProductBomItem.parent_product_id, ProductBomItem.component_id).where(
                    ProductBomItem.component_kind == COMPONENT_KIND_PRODUCT
                )
            )
        ).all()
        product_ids = list((await s.execute(select(Product.id))).scalars().all())

    children_of: dict = {p: set() for p in product_ids}
    for parent, child in adjacency_rows:
        children_of.setdefault(parent, set()).add(child)

    # Topological sort: children first.
    order: list = []
    seen: set = set()

    def _visit(node) -> None:
        if node in seen:
            return
        seen.add(node)
        for ch in children_of.get(node, ()):
            _visit(ch)
        order.append(node)

    for pid in product_ids:
        _visit(pid)

    async with factory() as s:
        for pid in order:
            tree = await bom_service.compute_cost_tree(s, product_id=pid)
            await s.execute(
                update(Product).where(Product.id == pid).values(unit_cost_cached=tree.total_cost)
            )
        await s.commit()

    async with factory() as s:
        rows = (await s.execute(select(Product).order_by(Product.id))).scalars().all()
        after = {r.id: r.unit_cost_cached for r in rows}

    assert after == before
