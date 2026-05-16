"""Within the grace period, no fee applies (Phase 7.6, #114)."""

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
async def test_within_grace_period_no_fee(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)

    # 32 days past due. Policy: apply_after_days=30 + grace_period_days=10
    # so threshold is 40 — invoice falls inside grace.
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="500.00",
        due_at=now - timedelta(days=32),
        state=InvoiceState.OVERDUE,
    )
    await policy_service.create(
        session,
        customer_id=None,
        kind="percent_of_outstanding",
        amount=Decimal("0.02"),
        apply_after_days=30,
        grace_period_days=10,
        actor_user_id=user.id,
    )

    result = await service.apply_late_fees(session=session, now=now)
    assert result.applied == 0


@pytest.mark.asyncio
async def test_past_grace_period_applies(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="500.00",
        due_at=now - timedelta(days=45),  # 45 days > 30 + 10 = 40 threshold
        state=InvoiceState.OVERDUE,
    )
    await policy_service.create(
        session,
        customer_id=None,
        kind="percent_of_outstanding",
        amount=Decimal("0.02"),
        apply_after_days=30,
        grace_period_days=10,
        actor_user_id=user.id,
    )

    result = await service.apply_late_fees(session=session, now=now)
    assert result.applied == 1
    assert result.fees_total == Decimal("10.00")
