"""Compound late-fee re-applies every N days (Phase 7.6, #114).

A ``compound_percent`` policy with a 30-day interval re-applies the
fee on day 60 (initial apply on day 30) and so on. The idempotency
guard uses the date of the most recent ``ar.LateFeeApplied`` event
on the invoice (fallback when Phase 7.4 debit notes aren't on main
yet — see ``apply_late_fees`` docstring).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.invoice import InvoiceState
from app.services import late_fee_policies as policy_service
from app.services import late_fees as service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._late_fees_helpers import (
    schema,  # noqa: F401
    seed_customer_simple,
    seed_issued_invoice,
    seed_user_simple,
)


@pytest.mark.asyncio
async def test_compound_reapplies_after_interval(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    base = datetime(2026, 1, 1, tzinfo=UTC)

    # Due_at was 60 days before our "now" of base.
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="1000.00",
        due_at=base - timedelta(days=60),
        state=InvoiceState.OVERDUE,
    )

    await policy_service.create(
        session,
        customer_id=None,
        kind="compound_percent",
        amount=Decimal("0.02"),  # 2 %
        grace_period_days=0,
        apply_after_days=30,
        compound_interval_days=30,
        actor_user_id=user.id,
    )

    # First run: day 60. Threshold is 30 — applies.
    r1 = await service.apply_late_fees(session=session, now=base)
    assert r1.applied == 1

    # 15 days later: within compound interval — no re-apply.
    r2 = await service.apply_late_fees(session=session, now=base + timedelta(days=15))
    assert r2.applied == 0

    # 30 days later: hits the next compound interval — re-apply.
    r3 = await service.apply_late_fees(session=session, now=base + timedelta(days=30))
    assert r3.applied == 1
