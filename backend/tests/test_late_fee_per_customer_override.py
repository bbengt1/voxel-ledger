"""Customer-specific policy beats the global one (Phase 7.6, #114)."""

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
async def test_customer_policy_beats_global(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session, display_name="VIP Co")
    now = datetime.now(UTC)
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="1000.00",
        due_at=now - timedelta(days=60),
        state=InvoiceState.OVERDUE,
    )

    # Global: 5 % — should be ignored for this customer.
    await policy_service.create(
        session,
        customer_id=None,
        kind="percent_of_outstanding",
        amount=Decimal("0.05"),
        apply_after_days=30,
        actor_user_id=user.id,
    )
    # Customer-specific: 1 % — wins.
    await policy_service.create(
        session,
        customer_id=customer.id,
        kind="percent_of_outstanding",
        amount=Decimal("0.01"),
        apply_after_days=30,
        actor_user_id=user.id,
    )

    result = await service.apply_late_fees(session=session, now=now)
    assert result.applied == 1
    # 1 % of 1000 = 10.00 (customer-specific), not 50.00 (global).
    assert result.fees_total == Decimal("10.00")


@pytest.mark.asyncio
async def test_resolve_returns_customer_specific(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    customer = await seed_customer_simple(session)
    await policy_service.create(
        session,
        customer_id=None,
        kind="flat",
        amount=Decimal("100"),
        actor_user_id=user.id,
    )
    cust_policy = await policy_service.create(
        session,
        customer_id=customer.id,
        kind="flat",
        amount=Decimal("5"),
        actor_user_id=user.id,
    )
    found = await policy_service.resolve_for_customer(session, customer_id=customer.id)
    assert found is not None
    assert found.id == cust_policy.id
