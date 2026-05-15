"""COGS post_for_sale integration tests (Phase 6.3, #95).

Confirming a product-line sale must:

* emit one ``inventory.TransactionRecorded`` per consumed FIFO lot
  (kind=``sale_consumption``),
* post ONE ``accounting.JournalEntryPosted`` with the correct debit /
  credit pairs (COGS, AR, Revenue, Inventory, optional Sales Tax /
  Channel Fees),
* run all of the above plus the state flip in the SAME database
  transaction — if the journal-entry post raises after inventory rows
  have been written, the whole thing must roll back atomically.
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
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.models.sale import SaleState
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

    # Sale row has the posting_journal_entry_id FK populated.
    from app.models.sale import Sale

    refreshed_sale = (
        await app_session.execute(select(Sale).where(Sale.id == sale.id))
    ).scalar_one()
    assert refreshed_sale.posting_journal_entry_id is not None

    # Journal entry exists with the expected description, and the sale's
    # FK points to it.
    je = (
        await app_session.execute(
            select(JournalEntry).where(
                JournalEntry.description == f"Sale {sale.sale_number}: posting"
            )
        )
    ).scalar_one()
    assert refreshed_sale.posting_journal_entry_id == je.id
    lines = (
        (await app_session.execute(select(JournalLine).where(JournalLine.entry_id == je.id)))
        .scalars()
        .all()
    )

    # COGS debit = 5*2 + 3*3 = 19; AR debit = total_amount (subtotal 160).
    cogs_debit = sum(line.debit for line in lines if line.account_id == defaults["cogs_account_id"])
    ar_debit = sum(line.debit for line in lines if line.account_id == defaults["ar_account_id"])
    revenue_credit = sum(
        line.credit for line in lines if line.account_id == defaults["revenue_account_id"]
    )
    inventory_credit = sum(
        line.credit for line in lines if line.account_id == defaults["inventory_account_id"]
    )
    assert cogs_debit == Decimal("19.000000")
    assert inventory_credit == Decimal("19.000000")
    # subtotal = 8 * 20 = 160
    assert ar_debit == Decimal("160.000000")
    assert revenue_credit == Decimal("160.000000")
    # Entry balances.
    total_debit = sum(line.debit for line in lines)
    total_credit = sum(line.credit for line in lines)
    assert total_debit == total_credit


@pytest.mark.asyncio
async def test_atomic_rollback_when_posting_fails(app_session: AsyncSession) -> None:
    """If the journal post raises after inventory rows are emitted, the
    outer transaction must roll back BOTH the state flip AND the
    inventory transactions. This is the v2 keystone invariant.

    We force a failure by deliberately misconfiguring the chart:
    archive the COGS account so journal_entries refuses to post against
    it. The inventory transactions have already been recorded by the
    time the journal post runs, so a successful rollback proves the
    same-TX guarantee.
    """
    from app.models.account import Account
    from sqlalchemy import update

    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _ = await _seed_product_with_lots(app_session, lots=[("5", "2.00")])
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
                "quantity": "3",
                "unit_price": "20.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    # Archive the COGS account so the journal post step raises.
    await app_session.execute(
        update(Account).where(Account.id == defaults["cogs_account_id"]).values(is_archived=True)
    )
    await app_session.commit()

    # Snapshot identifiers before the raise so we don't trigger
    # lazy-load on a rolled-back, expired ORM instance below.
    saved_sale_id = sale.id
    saved_sale_number = sale.sale_number

    from app.services import journal_entries as journal_service

    with pytest.raises(journal_service.AccountArchivedError):
        await sales_service.confirm(app_session, sale_id=saved_sale_id, actor_user_id=user.id)
    await app_session.rollback()

    # Open a fresh session on the running app's engine to verify the
    # rollback. We cannot reuse ``app_session`` after a service-level
    # raise + rollback because the in-memory aiosqlite connection was
    # mid-transaction and the next execute on the same session trips
    # MissingGreenlet on aiosqlite in some workloads.
    from app.core import db as db_module
    from app.models.sale import Sale

    factory = db_module._session_factory
    assert factory is not None
    async with factory() as fresh:
        refreshed_state = (
            await fresh.execute(select(Sale.state).where(Sale.id == saved_sale_id))
        ).scalar_one()
        state_value = (
            refreshed_state.value if isinstance(refreshed_state, SaleState) else refreshed_state
        )
        assert state_value == SaleState.DRAFT.value

        rows = (
            (
                await fresh.execute(
                    select(InventoryTransaction)
                    .where(InventoryTransaction.linked_sale_id == saved_sale_id)
                    .where(InventoryTransaction.kind == KIND_SALE_CONSUMPTION)
                )
            )
            .scalars()
            .all()
        )
        assert rows == []

        je = (
            await fresh.execute(
                select(JournalEntry).where(
                    JournalEntry.description == f"Sale {saved_sale_number}: posting"
                )
            )
        ).scalar_one_or_none()
        assert je is None
