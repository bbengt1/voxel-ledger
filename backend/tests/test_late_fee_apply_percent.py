"""Late-fee worker — percent_of_outstanding (Phase 7.6, #114).

Now that Phase 7.4 (``DebitNotesService``) has merged on main, the
worker actually issues a ``debit_note`` per application; ``deferred``
is always ``False``.
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
    seed_ar_posting_accounts,
    seed_customer_simple,
    seed_issued_invoice,
    seed_user_simple,
)


@pytest.mark.asyncio
async def test_percent_fee_applied_once(schema, session: AsyncSession) -> None:  # noqa: F811
    user = await seed_user_simple(session)
    await seed_ar_posting_accounts(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)

    # 60 days past due — over the default 30-day apply_after threshold.
    await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="1000.00",
        due_at=now - timedelta(days=60),
        state=InvoiceState.OVERDUE,
    )

    await policy_service.create(
        session,
        customer_id=None,
        kind="percent_of_outstanding",
        amount=Decimal("0.015"),  # 1.5%
        grace_period_days=0,
        apply_after_days=30,
        compound_interval_days=30,
        is_active=True,
        actor_user_id=user.id,
    )

    result = await service.apply_late_fees(session=session, now=now)
    assert result.applied == 1
    assert result.fees_total == Decimal("15.00")

    # Run again within the compound interval — must NOT re-apply.
    result2 = await service.apply_late_fees(session=session, now=now + timedelta(days=5))
    assert result2.applied == 0
    assert result2.skipped >= 1


@pytest.mark.asyncio
async def test_flat_fee_emits_debit_note(schema, session: AsyncSession) -> None:  # noqa: F811
    """With Phase 7.4 merged the worker creates a real ``debit_note``
    per application and never reports ``deferred=True``.
    """
    from app.models.credit_note import DebitNote
    from sqlalchemy import select

    user = await seed_user_simple(session)
    await seed_ar_posting_accounts(session)
    customer = await seed_customer_simple(session)
    now = datetime.now(UTC)
    invoice = await seed_issued_invoice(
        session,
        customer_id=customer.id,
        actor_user_id=user.id,
        total_amount="100.00",
        due_at=now - timedelta(days=60),
        state=InvoiceState.OVERDUE,
    )
    await policy_service.create(
        session,
        customer_id=None,
        kind="flat",
        amount=Decimal("25.00"),
        apply_after_days=30,
        actor_user_id=user.id,
    )
    result = await service.apply_late_fees(session=session, now=now)
    assert result.applied == 1
    assert result.deferred is False
    notes = list(
        (await session.execute(select(DebitNote).where(DebitNote.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    assert len(notes) == 1
    assert notes[0].reason == "late_fee"
    assert notes[0].total_amount == Decimal("25.00")
