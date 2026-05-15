"""sale_item kind/ref invariant: service AND DB layers (Phase 6.2, #94).

Exactly one of ``product_id`` / ``job_id`` is set OR both are null for
``kind=manual``. The service raises ``InvalidSaleItemError`` ahead of the
DB so callers get a friendly 400; a CHECK constraint at the DB is the
belt-and-suspenders backstop.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.sale import Sale, SaleItem, SaleItemKind, SaleState
from app.services import sales as sales_service
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel, seed_user


@pytest.mark.asyncio
async def test_service_rejects_product_kind_without_product_id(
    app_session: AsyncSession,
) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    with pytest.raises(sales_service.InvalidSaleItemError):
        await sales_service.create_draft(
            app_session,
            channel_id=channel.id,
            external_order_id=None,
            customer_name="X",
            customer_email=None,
            occurred_at=datetime.now(UTC),
            items=[
                {
                    "kind": "product",
                    "description": "missing product id",
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
            actor_user_id=user.id,
        )


@pytest.mark.asyncio
async def test_service_rejects_manual_with_product_id(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    with pytest.raises(sales_service.InvalidSaleItemError):
        await sales_service.create_draft(
            app_session,
            channel_id=channel.id,
            external_order_id=None,
            customer_name="X",
            customer_email=None,
            occurred_at=datetime.now(UTC),
            items=[
                {
                    "kind": "manual",
                    "product_id": str(uuid.uuid4()),
                    "description": "free-form but with product",
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
            actor_user_id=user.id,
        )


@pytest.mark.asyncio
async def test_service_rejects_unknown_product_id(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    with pytest.raises(sales_service.InvalidSaleItemError):
        await sales_service.create_draft(
            app_session,
            channel_id=channel.id,
            external_order_id=None,
            customer_name="X",
            customer_email=None,
            occurred_at=datetime.now(UTC),
            items=[
                {
                    "kind": "product",
                    "product_id": str(uuid.uuid4()),
                    "description": "ghost",
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
            actor_user_id=user.id,
        )


@pytest.mark.asyncio
async def test_db_check_constraint_blocks_manual_with_product_id(
    app_session: AsyncSession,
) -> None:
    """If the service guard is bypassed (synthetic direct insert), the DB
    CHECK constraint still blocks the bad row."""
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)
    sale = Sale(
        sale_number="SO-TEST-9999",
        channel_id=channel.id,
        customer_name="X",
        occurred_at=datetime.now(UTC),
        subtotal=Decimal("0"),
        discount_amount=Decimal("0"),
        shipping_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        channel_fee_amount=Decimal("0"),
        total_amount=Decimal("0"),
        state=SaleState.DRAFT,
        created_by_user_id=user.id,
    )
    app_session.add(sale)
    await app_session.flush()

    bad_item = SaleItem(
        sale_id=sale.id,
        line_number=1,
        kind=SaleItemKind.MANUAL,
        # Violates the CHECK constraint — manual must have neither set.
        product_id=uuid.uuid4(),
        description="bad",
        quantity=Decimal("1"),
        unit_price=Decimal("1"),
        extended_amount=Decimal("1"),
    )
    app_session.add(bad_item)
    with pytest.raises(IntegrityError):
        await app_session.flush()
    await app_session.rollback()
