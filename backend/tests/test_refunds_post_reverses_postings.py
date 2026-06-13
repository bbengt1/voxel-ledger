"""Posted full refund: inventory nets to zero and the reversing entry is
enqueued for QBO (Phase 6.5; QBO-sole-ledger since epic #312, Phase 5e)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.inventory_transaction import (
    KIND_RETURN_IN,
    KIND_SALE_CONSUMPTION,
    InventoryTransaction,
)
from app.models.qbo_sync_outbox import QboSyncOutbox
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

    # QBO is the sole ledger (epic #312, Phase 5e): the reversing entry is
    # enqueued on the sync outbox instead of posted locally. For a full
    # refund with restock the role-tagged legs are: Dr revenue / Cr bank for
    # the cash, plus Dr inventory / Cr cogs for the restocked cost.
    assert refund.posting_journal_entry_id is None
    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "refund", QboSyncOutbox.local_id == refund.id
            )
        )
    ).scalar_one()
    by_role = {
        ln["role"]: (ln["posting"], Decimal(ln["amount"])) for ln in outbox_row.payload["lines"]
    }
    assert by_role["revenue"] == ("debit", Decimal("40.00"))
    assert by_role["bank"] == ("credit", Decimal("40.00"))
    assert by_role["inventory"] == ("debit", Decimal("12.00"))
    assert by_role["cogs"] == ("credit", Decimal("12.00"))
    debits = sum(amt for posting, amt in by_role.values() if posting == "debit")
    credits = sum(amt for posting, amt in by_role.values() if posting == "credit")
    assert debits == credits
