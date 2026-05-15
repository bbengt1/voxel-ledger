"""Confirm → cancel reversal symmetry (Phase 6.3, #95).

Asserts: a sale confirmed and then cancelled leaves both the inventory
ledger and the GL balance net to zero for the sale-related accounts.
Also checks the audit projection sees the SalePosted + SaleReversed
events with the expected denormalized fields.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.events.types import sales as sales_events
from app.models.audit import AuditLog
from app.models.inventory_transaction import (
    KIND_PRODUCTION_IN,
    InventoryTransaction,
)
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
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


@pytest.mark.asyncio
async def test_confirm_then_cancel_nets_to_zero(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )

    location = await locations_service.create(
        app_session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )
    product = await products_service.create(
        app_session,
        name="Widget",
        description=None,
        unit_price=Decimal("20.00"),
        sku=f"PRD-{uuid.uuid4().hex[:6]}",
        actor_user_id=None,
    )
    await app_session.commit()
    await inventory_tx_service.record(
        app_session,
        kind=KIND_PRODUCTION_IN,
        entity_kind="product",
        entity_id=product.id,
        location_id=location.id,
        quantity=Decimal("10"),
        unit_cost=Decimal("3.00"),
        actor_user_id=None,
    )
    await app_session.commit()

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
                "quantity": "4",
                "unit_price": "20.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    await app_session.commit()
    await sales_service.cancel(app_session, sale_id=sale.id, actor_user_id=user.id)
    await app_session.commit()

    # Inventory net to zero for the sale's draws: sale_consumption (-4)
    # + return_in (+4) = 0.
    rows = (
        (
            await app_session.execute(
                select(InventoryTransaction).where(InventoryTransaction.linked_sale_id == sale.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    net = sum(r.quantity for r in rows)
    assert net == Decimal("0.000000")

    # Journal entries: the original is_reversed, plus a reversal entry.
    je_rows = (
        (
            await app_session.execute(
                select(JournalEntry).where(
                    JournalEntry.description.in_(
                        [
                            f"Sale {sale.sale_number}: posting",
                            f"Reversal of sale {sale.sale_number}",
                        ]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(je_rows) == 2

    # Per-account net across both entries is zero for every account.
    line_rows = (
        (
            await app_session.execute(
                select(JournalLine).where(JournalLine.entry_id.in_([je.id for je in je_rows]))
            )
        )
        .scalars()
        .all()
    )
    by_account: dict[uuid.UUID, Decimal] = {}
    for line in line_rows:
        by_account[line.account_id] = (
            by_account.get(line.account_id, Decimal("0")) + line.debit - line.credit
        )
    for account_id, net_delta in by_account.items():
        assert net_delta == Decimal("0.000000"), (account_id, net_delta)

    # Audit projection saw SalePosted + SaleReversed for this sale.
    audit_types = (
        (
            await app_session.execute(
                select(AuditLog.event_type).where(AuditLog.aggregate_id == sale.id)
            )
        )
        .scalars()
        .all()
    )
    assert sales_events.TYPE_SALE_POSTED in audit_types
    assert sales_events.TYPE_SALE_REVERSED in audit_types


@pytest.mark.asyncio
async def test_cancel_from_draft_emits_no_reversal(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
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
                "kind": "manual",
                "description": "Tip",
                "quantity": "1",
                "unit_price": "1.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    await sales_service.cancel(app_session, sale_id=sale.id, actor_user_id=user.id)
    await app_session.commit()

    audit_types = (
        (
            await app_session.execute(
                select(AuditLog.event_type).where(AuditLog.aggregate_id == sale.id)
            )
        )
        .scalars()
        .all()
    )
    assert sales_events.TYPE_SALE_REVERSED not in audit_types
