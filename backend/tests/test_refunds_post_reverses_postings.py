"""Posted refund net-zero on inventory + GL for a full refund (Phase 6.5)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.inventory_transaction import (
    KIND_RETURN_IN,
    KIND_SALE_CONSUMPTION,
    InventoryTransaction,
)
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.models.refund import RefundState
from app.services import refunds as refunds_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._refunds_helpers import create_confirmed_sale, seed_product_with_stock
from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user


@pytest.mark.asyncio
async def test_full_refund_post_net_zero(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _ = await seed_product_with_stock(app_session, qty="10", unit_cost="3.00")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="4",
        unit_price="10.00",
    )
    sale_item = sale.items[0]

    # Create a full refund (under default $500 threshold so auto-approved).
    result = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="full",
        reason_code="damaged",
        notes=None,
        restock_inventory=True,
        items=[
            {
                "sale_item_id": str(sale_item.id),
                "quantity": "4",
                "unit_amount": "10.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.refund.state == RefundState.APPROVED

    # Post.
    await refunds_service.post(result.refund.id, session=app_session, actor_user_id=user.id)
    await app_session.commit()

    refund = await refunds_service.get(result.refund.id, session=app_session)
    assert refund.state == RefundState.POSTED

    # Inventory: net zero on the product.
    sale_consumption_rows = (
        (
            await app_session.execute(
                select(InventoryTransaction)
                .where(InventoryTransaction.linked_sale_id == sale.id)
                .where(InventoryTransaction.kind == KIND_SALE_CONSUMPTION)
            )
        )
        .scalars()
        .all()
    )
    return_rows = (
        (
            await app_session.execute(
                select(InventoryTransaction)
                .where(InventoryTransaction.linked_sale_id == sale.id)
                .where(InventoryTransaction.kind == KIND_RETURN_IN)
            )
        )
        .scalars()
        .all()
    )
    consumed_total = sum(-r.quantity for r in sale_consumption_rows)
    restored_total = sum(r.quantity for r in return_rows)
    assert consumed_total == restored_total == Decimal("4.000000")

    # GL: original posting + reversing entry. Net per-account = 0.
    je_rows = (
        (
            await app_session.execute(
                select(JournalLine).join(JournalEntry).where(JournalLine.entry_id.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    # Compute net debit - credit per account across BOTH the sale posting
    # and the refund reversal. For a full refund, these should sum to 0
    # for each touched account.
    net: dict = {}
    for line in je_rows:
        delta = line.debit - line.credit
        net[line.account_id] = net.get(line.account_id, Decimal("0")) + delta
    for account_id, delta in net.items():
        assert delta == Decimal(
            "0"
        ), f"account {account_id} net {delta} expected 0 after full refund"
