"""restock_inventory=False enqueues the QBO reversal but no inventory
transactions (Phase 6.5; QBO-sole-ledger since epic #312, Phase 5e)."""

from __future__ import annotations

import pytest
from app.models.inventory_transaction import KIND_RETURN_IN, InventoryTransaction
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.services import refunds as refunds_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._refunds_helpers import create_confirmed_sale, seed_product_with_stock
from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user


@pytest.mark.asyncio
async def test_post_without_restock_skips_inventory(
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
    product, _ = await seed_product_with_stock(app_session, qty="10", unit_cost="3")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="2",
        unit_price="10.00",
    )
    sale_item = sale.items[0]
    result = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="full",
        reason_code="damaged",
        notes=None,
        restock_inventory=False,
        items=[
            {
                "sale_item_id": str(sale_item.id),
                "quantity": "2",
                "unit_amount": "10.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()
    await refunds_service.post(result.refund.id, session=app_session, actor_user_id=user.id)
    await app_session.commit()

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
    assert return_rows == []

    # The reversal still happens — QBO is the sole ledger (epic #312,
    # Phase 5e), so it goes out via the sync outbox instead of a local JE.
    refund = await refunds_service.get(result.refund.id, session=app_session)
    assert refund.posting_journal_entry_id is None
    outbox_row = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "refund", QboSyncOutbox.local_id == refund.id
            )
        )
    ).scalar_one()
    roles = {ln["role"] for ln in outbox_row.payload["lines"]}
    # No restock → no inventory/cogs legs.
    assert "inventory" not in roles
    assert "cogs" not in roles
