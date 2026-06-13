"""COGS post_for_sale integration tests (Phase 6.3, #95).

Confirming a product-line sale must:

* emit one ``inventory.TransactionRecorded`` per consumed FIFO lot
  (kind=``sale_consumption``),
* enqueue the QBO documents via the sync outbox — QBO is the sole
  ledger (epic #312, Phase 5e): a native ``sale`` doc plus a
  ``sale_cogs`` JournalEntry spec carrying the FIFO cost.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.inventory_transaction import (
    KIND_PRODUCTION_IN,
    KIND_SALE_CONSUMPTION,
    InventoryTransaction,
)
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as inventory_tx_service
from app.services import products as products_service
from app.services import sales as sales_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import (
    seed_channel,
    seed_posting_defaults,
    seed_user,
)


async def _seed_product_with_lots(
    session: AsyncSession,
    *,
    lots: list[tuple[str, str]],
):
    """Create a product, a workshop location, and the given lots
    (qty, unit_cost) via ``production_in`` rows."""
    location = await locations_service.create(
        session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )
    product = await products_service.create(
        session,
        name="Widget",
        description=None,
        unit_price=Decimal("20.00"),
        sku=f"PRD-{uuid.uuid4().hex[:6]}",
        actor_user_id=None,
    )
    await session.commit()
    base_ts = datetime.now(UTC)
    for idx, (qty, cost) in enumerate(lots):
        from datetime import timedelta

        await inventory_tx_service.record(
            session,
            kind=KIND_PRODUCTION_IN,
            entity_kind="product",
            entity_id=product.id,
            location_id=location.id,
            quantity=Decimal(qty),
            unit_cost=Decimal(cost),
            occurred_at=base_ts + timedelta(seconds=idx),
            actor_user_id=None,
        )
        await session.commit()
    return product, location


@pytest.mark.asyncio
async def test_confirm_emits_inventory_transactions_and_journal_entry(
    app_session: AsyncSession,
) -> None:
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _location = await _seed_product_with_lots(
        app_session,
        lots=[("5", "2.00"), ("5", "3.00")],
    )

    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="C",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=[
            {
                "kind": "product",
                "product_id": str(product.id),
                "description": "Widget",
                "quantity": "8",
                "unit_price": "20.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    await app_session.commit()

    # Inventory: 2 sale_consumption rows (5 from lot1, 3 from lot2).
    rows = (
        (
            await app_session.execute(
                select(InventoryTransaction)
                .where(InventoryTransaction.linked_sale_id == sale.id)
                .where(InventoryTransaction.kind == KIND_SALE_CONSUMPTION)
                .order_by(InventoryTransaction.occurred_at, InventoryTransaction.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    # Quantities are stored negative for sale_consumption.
    assert sum(-r.quantity for r in rows) == Decimal("8.000000")
    costs = sorted(r.unit_cost_at_transaction for r in rows)
    assert Decimal("2.000000") in costs and Decimal("3.000000") in costs

    # QBO is the sole ledger: no local JE FK on the sale.
    from app.models.sale import Sale

    refreshed_sale = (
        await app_session.execute(select(Sale).where(Sale.id == sale.id))
    ).scalar_one()
    assert refreshed_sale.posting_journal_entry_id is None

    # Outbox carries the native sale doc + the COGS JournalEntry spec.
    outbox_rows = (
        (
            await app_session.execute(
                select(QboSyncOutbox).where(QboSyncOutbox.local_id == sale.id)
            )
        )
        .scalars()
        .all()
    )
    by_kind = {row.kind: row for row in outbox_rows}
    assert set(by_kind) == {"sale", "sale_cogs"}
    assert by_kind["sale"].op == "post"
    # subtotal = 8 * 20 = 160
    assert Decimal(by_kind["sale"].payload["lines"][0]["amount"]) == Decimal("160.00")

    # COGS = 5*2 + 3*3 = 19, debited to COGS and credited from inventory.
    cogs_lines = by_kind["sale_cogs"].payload["lines"]
    by_role = {(line["role"], line["posting"]): Decimal(line["amount"]) for line in cogs_lines}
    assert by_role[("cogs", "debit")] == Decimal("19.000000")
    assert by_role[("inventory", "credit")] == Decimal("19.000000")
