"""AR aging report buckets + CSV format (Phase 7.6, #114)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.invoice import InvoiceState
from app.services.reports import ar_aging
from sqlalchemy.ext.asyncio import AsyncSession

from tests._late_fees_helpers import (
    schema,  # noqa: F401
    seed_customer_simple,
    seed_issued_invoice,
    seed_user_simple,
)


@pytest.mark.asyncio
async def test_invoices_bucket_correctly(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session, display_name="Bucketed Co")
    now = datetime(2026, 6, 1, tzinfo=UTC)

    # Four invoices, one in each bucket.
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="10.00",
        due_at=now - timedelta(days=5),  # 0-30 bucket
        state=InvoiceState.ISSUED,
    )
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="20.00",
        due_at=now - timedelta(days=45),  # 31-60
        state=InvoiceState.OVERDUE,
    )
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="30.00",
        due_at=now - timedelta(days=75),  # 61-90
        state=InvoiceState.OVERDUE,
    )
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="40.00",
        due_at=now - timedelta(days=120),  # 91+
        state=InvoiceState.OVERDUE,
    )

    report = await ar_aging.build_ar_aging(session=session, as_of=now, bucket_days=[30, 60, 90])
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.total_outstanding == Decimal("100.00")
    by_label = {b.label: b.amount for b in row.buckets}
    assert by_label["0-30"] == Decimal("10.00")
    assert by_label["31-60"] == Decimal("20.00")
    assert by_label["61-90"] == Decimal("30.00")
    assert by_label["91+"] == Decimal("40.00")
    assert report.grand_total == Decimal("100.00")


@pytest.mark.asyncio
async def test_csv_has_header(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session, display_name="CSV Co")
    now = datetime.now(UTC)
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="50.00",
        due_at=now - timedelta(days=10),
    )

    report = await ar_aging.build_ar_aging(session=session, as_of=now, bucket_days=[30, 60, 90])
    csv_text = ar_aging.render_csv(report)
    lines = csv_text.strip().split("\n")
    header = lines[0]
    assert "customer_number" in header
    assert "display_name" in header
    assert "total_outstanding" in header
    assert "0-30" in header
    assert "91+" in header
    # Includes a TOTAL row.
    assert any("TOTAL" in line for line in lines)


@pytest.mark.asyncio
async def test_void_and_zero_outstanding_excluded(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)

    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="100.00",
        due_at=now - timedelta(days=10),
        state=InvoiceState.VOID,
    )
    # zero-outstanding invoice
    zero = await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="100.00",
        due_at=now - timedelta(days=10),
        state=InvoiceState.PAID,
    )
    zero.amount_outstanding = Decimal("0")
    await session.flush()

    report = await ar_aging.build_ar_aging(session=session, as_of=now, bucket_days=[30, 60, 90])
    assert report.grand_total == Decimal("0")
    assert report.rows == []


@pytest.mark.asyncio
async def test_parse_bucket_query() -> None:
    assert ar_aging.parse_bucket_query(None, [30, 60, 90]) == [30, 60, 90]
    assert ar_aging.parse_bucket_query("0,30,60,90,120", [30, 60, 90]) == [30, 60, 90, 120]
    assert ar_aging.parse_bucket_query("30,60", [30, 60, 90]) == [30, 60]

    with pytest.raises(ValueError):
        ar_aging.parse_bucket_query("60,30", [30, 60, 90])
    with pytest.raises(ValueError):
        ar_aging.parse_bucket_query("-5", [30, 60, 90])
