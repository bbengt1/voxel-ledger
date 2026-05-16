"""AR aging report performance budget (Phase 7.6, #114).

Marked ``benchmark`` because on a tiny in-memory SQLite this is more
of a sanity check than a real perf gate — the spec calls for < 500 ms
p95 against a populated PG (1000 customers, 10k invoices). Locally
we seed a smaller corpus (50 customers, 500 invoices) and assert
the call returns in < 500 ms, which is a strict lower bound on the
real perf budget.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.invoice import Invoice, InvoiceState
from app.services.reports import ar_aging
from sqlalchemy.ext.asyncio import AsyncSession

from tests._late_fees_helpers import (
    schema,  # noqa: F401
    seed_customer_simple,
    seed_user_simple,
)


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_ar_aging_perf_budget(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    now = datetime(2026, 6, 1, tzinfo=UTC)

    customers = []
    for i in range(50):
        c = await seed_customer_simple(session, display_name=f"Cust {i:03d}")
        customers.append(c)
    await session.flush()

    invoices = []
    for ci, customer in enumerate(customers):
        for j in range(10):
            days = (ci * 7 + j * 11) % 200 + 1
            total = Decimal(str((ci + 1) * (j + 1) * 1.5))
            invoices.append(
                Invoice(
                    invoice_number=f"INV-PERF-{uuid.uuid4().hex[:10]}",
                    customer_id=customer.id,
                    state=InvoiceState.OVERDUE,
                    issued_at=now - timedelta(days=days + 30),
                    due_at=now - timedelta(days=days),
                    subtotal=total,
                    discount_amount=Decimal("0"),
                    tax_amount=Decimal("0"),
                    total_amount=total,
                    amount_paid=Decimal("0"),
                    amount_outstanding=total,
                    currency="USD",
                    created_by_user_id=user.id,
                )
            )
    session.add_all(invoices)
    await session.flush()

    start = time.perf_counter()
    report = await ar_aging.build_ar_aging(session=session, as_of=now, bucket_days=[30, 60, 90])
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(report.rows) == 50
    # Strict lower bound for the 500 ms p95 PG budget.
    assert elapsed_ms < 500, f"AR aging took {elapsed_ms:.1f}ms (budget 500)"
