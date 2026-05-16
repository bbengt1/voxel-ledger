"""Overdue marker worker (Phase 7.6, #114).

Sweeps ``due_at < now() AND state IN (issued, partially_paid)`` and
flips the row to ``state=overdue``. Idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.invoice import InvoiceState
from app.services import late_fees as service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._late_fees_helpers import (
    schema,  # noqa: F401
    seed_customer_simple,
    seed_issued_invoice,
    seed_user_simple,
)


@pytest.mark.asyncio
async def test_marks_past_due_invoice_overdue(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)
    inv = await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        due_at=now - timedelta(days=5),
    )

    result = await service.mark_overdue_invoices(session=session, now=now)
    assert result.marked == 1
    await session.refresh(inv)
    assert inv.state == InvoiceState.OVERDUE


@pytest.mark.asyncio
async def test_not_yet_due_stays_issued(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)
    inv = await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        due_at=now + timedelta(days=5),
    )

    result = await service.mark_overdue_invoices(session=session, now=now)
    assert result.marked == 0
    await session.refresh(inv)
    assert inv.state == InvoiceState.ISSUED


@pytest.mark.asyncio
async def test_idempotent(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        due_at=now - timedelta(days=10),
    )

    first = await service.mark_overdue_invoices(session=session, now=now)
    second = await service.mark_overdue_invoices(session=session, now=now)
    assert first.marked == 1
    assert second.marked == 0


@pytest.mark.asyncio
async def test_partially_paid_also_marked(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)
    inv = await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        due_at=now - timedelta(days=3),
        state=InvoiceState.PARTIALLY_PAID,
    )

    result = await service.mark_overdue_invoices(session=session, now=now)
    assert result.marked == 1
    await session.refresh(inv)
    assert inv.state == InvoiceState.OVERDUE
