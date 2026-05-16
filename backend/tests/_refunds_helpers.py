"""Shared helpers for refund tests (Phase 6.5, #97)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as inventory_tx_service
from app.services import products as products_service
from app.services import sales as sales_service
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_product_with_stock(
    session: AsyncSession,
    *,
    qty: str = "20",
    unit_cost: str = "5.00",
    sku_suffix: str | None = None,
):
    """Seed a product with one production_in lot in a workshop."""
    location = await locations_service.create(
        session,
        name="WS",
        code=f"WS-{uuid.uuid4().hex[:4]}",
        kind="workshop",
        actor_user_id=None,
    )
    suffix = sku_suffix or uuid.uuid4().hex[:6]
    product = await products_service.create(
        session,
        name=f"Widget-{suffix}",
        description=None,
        unit_price=Decimal("20.00"),
        sku=f"PRD-{suffix}",
        actor_user_id=None,
    )
    await session.commit()
    await inventory_tx_service.record(
        session,
        kind="production_in",
        entity_kind="product",
        entity_id=product.id,
        location_id=location.id,
        quantity=Decimal(qty),
        unit_cost=Decimal(unit_cost),
        occurred_at=datetime.now(UTC) - timedelta(seconds=1),
        actor_user_id=None,
    )
    await session.commit()
    return product, location


async def create_confirmed_sale(
    session: AsyncSession,
    *,
    channel,
    user,
    product,
    quantity: str = "2",
    unit_price: str = "20.00",
):
    """Create + confirm a sale with one product line. Posts inventory + GL."""
    sale = await sales_service.create_draft(
        session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="Customer",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=[
            {
                "kind": "product",
                "product_id": str(product.id),
                "description": "Widget",
                "quantity": quantity,
                "unit_price": unit_price,
            }
        ],
        actor_user_id=user.id,
    )
    await session.commit()
    await sales_service.confirm(session, sale_id=sale.id, actor_user_id=user.id)
    await session.commit()
    # Re-load fresh so the caller has populated FK.
    sale = await sales_service.get(session, sale.id)
    return sale
