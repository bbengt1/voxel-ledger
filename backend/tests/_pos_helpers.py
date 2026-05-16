"""Shared helpers for POS tests (Phase 6.4, #96)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.services import inventory_locations as locations_service
from app.services import inventory_transactions as inventory_tx_service
from app.services import products as products_service
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_pos_channel(
    session: AsyncSession,
    *,
    default_revenue_account_id: uuid.UUID | None = None,
):
    """Create a POS-kind channel."""
    from app.services import sales_channels as channels_service

    suffix = uuid.uuid4().hex[:6]
    channel = await channels_service.create(
        session,
        name=f"POS-{suffix}",
        slug=f"pos-{suffix}",
        kind="pos",
        fee_model="none",
        fee_percent=None,
        fee_flat=None,
        default_revenue_account_id=default_revenue_account_id,
        default_fee_account_id=None,
        actor_user_id=None,
    )
    await session.commit()
    return channel


async def seed_product_with_barcode(
    session: AsyncSession,
    *,
    barcode: str,
    unit_price: str = "10.00",
    name: str | None = None,
):
    """Seed a product with the supplied barcode (==upc) and unique SKU."""
    suffix = uuid.uuid4().hex[:6]
    product = await products_service.create(
        session,
        name=name or f"Widget-{suffix}",
        description=None,
        unit_price=Decimal(unit_price),
        sku=f"PRD-{suffix}",
        upc=barcode,
        actor_user_id=None,
    )
    await session.commit()
    return product


async def seed_product_with_inventory(
    session: AsyncSession,
    *,
    barcode: str,
    unit_price: str = "20.00",
    qty_on_hand: str = "100",
    unit_cost: str = "5.00",
):
    """Seed a product + workshop + an inventory lot via production_in.

    Use this when the test will check out the cart (so the COGS service
    has FIFO lots to consume).
    """
    from datetime import UTC, datetime

    from app.models.inventory_transaction import KIND_PRODUCTION_IN

    product = await seed_product_with_barcode(session, barcode=barcode, unit_price=unit_price)
    suffix = uuid.uuid4().hex[:6]
    location = await locations_service.create(
        session, name=f"WS-{suffix}", code=f"WS{suffix}", kind="workshop", actor_user_id=None
    )
    await session.commit()
    await inventory_tx_service.record(
        session,
        kind=KIND_PRODUCTION_IN,
        entity_kind="product",
        entity_id=product.id,
        location_id=location.id,
        quantity=Decimal(qty_on_hand),
        unit_cost=Decimal(unit_cost),
        occurred_at=datetime.now(UTC),
        actor_user_id=None,
    )
    await session.commit()
    return product, location
