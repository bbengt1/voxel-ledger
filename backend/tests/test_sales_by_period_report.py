"""Sales-by-period report tests (Phase 10.5, #180)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.refund import Refund, RefundKind, RefundState
from app.models.sale import Sale, SaleState
from app.services.reports import sales_by_period as report_service
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import seed_owner
from tests._sales_helpers import seed_channel


async def _insert_sale(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    user_id: uuid.UUID,
    total: str,
    occurred_at: datetime,
    state: SaleState = SaleState.CONFIRMED,
) -> Sale:
    sale_id = uuid.uuid4()
    sale = Sale(
        id=sale_id,
        sale_number=f"SALE-TEST-{sale_id.hex[:8]}",
        channel_id=channel_id,
        external_order_id=None,
        customer_name="Test",
        occurred_at=occurred_at,
        subtotal=Decimal(total),
        discount_amount=Decimal("0"),
        shipping_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        channel_fee_amount=Decimal("0"),
        total_amount=Decimal(total),
        state=state,
        created_by_user_id=user_id,
        created_at=occurred_at,
        updated_at=occurred_at,
    )
    session.add(sale)
    await session.flush()
    return sale


async def _insert_refund(
    session: AsyncSession,
    *,
    sale: Sale,
    user_id: uuid.UUID,
    total: str,
    created_at: datetime,
    state: RefundState = RefundState.POSTED,
) -> Refund:
    rid = uuid.uuid4()
    refund = Refund(
        id=rid,
        refund_number=f"RF-TEST-{rid.hex[:8]}",
        sale_id=sale.id,
        kind=RefundKind.PARTIAL,
        state=state,
        total_amount=Decimal(total),
        reason_code="test",
        created_by_user_id=user_id,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(refund)
    await session.flush()
    return refund


@pytest.mark.asyncio
async def test_month_bucket(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    channel = await seed_channel(app_session)
    today = datetime.now(UTC)
    last_month = today.replace(day=1) - timedelta(days=15)
    await _insert_sale(
        app_session, channel_id=channel.id, user_id=user.id, total="100.00", occurred_at=today
    )
    await _insert_sale(
        app_session, channel_id=channel.id, user_id=user.id, total="50.00", occurred_at=today
    )
    await _insert_sale(
        app_session,
        channel_id=channel.id,
        user_id=user.id,
        total="75.00",
        occurred_at=last_month,
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=last_month.date(),
        date_to=today.date(),
        bucket="month",
    )
    assert len(report.rows) == 2
    by_start = {r.bucket_start: r for r in report.rows}
    assert by_start[last_month.replace(day=1).date()].gross_sales == Decimal("75.00")
    assert by_start[last_month.replace(day=1).date()].order_count == 1
    assert by_start[today.replace(day=1).date()].gross_sales == Decimal("150.00")
    assert by_start[today.replace(day=1).date()].order_count == 2
    assert report.total_gross == Decimal("225.00")
    assert report.total_orders == 3


@pytest.mark.asyncio
async def test_refund_subtracts(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    channel = await seed_channel(app_session)
    today = datetime.now(UTC)
    sale = await _insert_sale(
        app_session, channel_id=channel.id, user_id=user.id, total="100.00", occurred_at=today
    )
    await _insert_refund(app_session, sale=sale, user_id=user.id, total="30.00", created_at=today)
    # Rejected refund should NOT count.
    await _insert_refund(
        app_session,
        sale=sale,
        user_id=user.id,
        total="999.00",
        created_at=today,
        state=RefundState.REJECTED,
    )
    # Cancelled sale should NOT count.
    await _insert_sale(
        app_session,
        channel_id=channel.id,
        user_id=user.id,
        total="500.00",
        occurred_at=today,
        state=SaleState.CANCELLED,
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
    )
    assert report.total_gross == Decimal("100.00")
    assert report.total_refunds == Decimal("30.00")
    assert report.total_net == Decimal("70.00")


@pytest.mark.asyncio
async def test_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await seed_owner(app_session)
    channel = await seed_channel(app_session)
    today = datetime.now(UTC)
    await _insert_sale(
        app_session, channel_id=channel.id, user_id=user.id, total="10.00", occurred_at=today
    )
    await app_session.commit()

    report = await report_service.build(
        app_session,
        date_from=today.date() - timedelta(days=1),
        date_to=today.date() + timedelta(days=1),
        bucket="day",
    )
    csv = report_service.to_csv(report)
    rows = csv.strip().splitlines()
    assert rows[0].split(",")[0] == "channel_id"
    assert any(line.startswith("GRAND TOTAL,") for line in rows)
