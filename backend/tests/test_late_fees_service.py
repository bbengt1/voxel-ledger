"""Late-fee applicator service tests (Phase 7.6, #114)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.credit_note import DebitNote
from app.models.invoice import InvoiceState
from app.models.late_fee_policy import LateFeeKind
from app.services import late_fees as service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._late_fees_helpers import (
    get_invoice,
    seed_customer,
    seed_full_ar_stack,
    seed_issued_invoice,
)
from tests._payments_helpers import token_for


async def _setup(app_session: AsyncSession, client: AsyncClient, *, price: str = "100.00"):
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price=price
    )
    fresh = await get_invoice(app_session, invoice.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=45)
    fresh.state = InvoiceState.OVERDUE
    await app_session.commit()
    return customer, user, invoice


@pytest.mark.asyncio
async def test_percent_of_outstanding_applies_once(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    _, user, invoice = await _setup(app_session, client)
    await service.create_policy(
        app_session,
        kind=LateFeeKind.PERCENT_OF_OUTSTANDING,
        amount=Decimal("0.015"),
        apply_after_days=30,
        actor_user_id=user.id,
    )
    await app_session.commit()

    first = await service.apply_late_fees(session=app_session)
    await app_session.commit()
    assert len(first) == 1
    assert first[0].amount == Decimal("1.50")

    # A debit note exists with reason late_fee.
    notes = (await app_session.execute(select(DebitNote))).scalars().all()
    assert len(notes) == 1
    assert notes[0].reason == "late_fee"

    # Outstanding bumped on the invoice.
    refreshed = await get_invoice(app_session, invoice.id)
    assert refreshed.amount_outstanding == Decimal("101.500000")
    assert refreshed.last_late_fee_applied_at is not None

    # Second run is a no-op (percent_of_outstanding is one-shot).
    second = await service.apply_late_fees(session=app_session)
    await app_session.commit()
    assert second == []


@pytest.mark.asyncio
async def test_flat_late_fee(client: AsyncClient, app_session: AsyncSession) -> None:
    _, user, invoice = await _setup(app_session, client)
    await service.create_policy(
        app_session,
        kind=LateFeeKind.FLAT,
        amount=Decimal("25.00"),
        apply_after_days=30,
        actor_user_id=user.id,
    )
    await app_session.commit()

    results = await service.apply_late_fees(session=app_session)
    await app_session.commit()
    assert len(results) == 1
    assert results[0].amount == Decimal("25.00")


@pytest.mark.asyncio
async def test_compound_percent_reapplies_after_interval(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    _, user, invoice = await _setup(app_session, client)
    await service.create_policy(
        app_session,
        kind=LateFeeKind.COMPOUND_PERCENT,
        amount=Decimal("0.01"),
        apply_after_days=30,
        compound_interval_days=30,
        actor_user_id=user.id,
    )
    await app_session.commit()

    now0 = datetime.now(UTC)
    first = await service.apply_late_fees(session=app_session, now=now0)
    await app_session.commit()
    assert len(first) == 1

    # Within the compound interval → no re-application.
    soon = now0 + timedelta(days=10)
    second = await service.apply_late_fees(session=app_session, now=soon)
    await app_session.commit()
    assert second == []

    # Past the interval → another fee.
    later = now0 + timedelta(days=35)
    third = await service.apply_late_fees(session=app_session, now=later)
    await app_session.commit()
    assert len(third) == 1


@pytest.mark.asyncio
async def test_grace_period_blocks_application(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    _, user, invoice = await _setup(app_session, client)
    # Move due_at to just 5 days ago + grace period 10 → within grace.
    fresh = await get_invoice(app_session, invoice.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=5)
    await app_session.commit()
    await service.create_policy(
        app_session,
        kind=LateFeeKind.FLAT,
        amount=Decimal("10.00"),
        grace_period_days=10,
        apply_after_days=0,
        actor_user_id=user.id,
    )
    await app_session.commit()

    results = await service.apply_late_fees(session=app_session)
    await app_session.commit()
    assert results == []


@pytest.mark.asyncio
async def test_per_customer_policy_beats_global(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer, user, invoice = await _setup(app_session, client)
    # Global policy: 1% percent.
    await service.create_policy(
        app_session,
        kind=LateFeeKind.PERCENT_OF_OUTSTANDING,
        amount=Decimal("0.01"),
        apply_after_days=30,
        actor_user_id=user.id,
    )
    # Per-customer override: flat $5.
    await service.create_policy(
        app_session,
        customer_id=customer.id,
        kind=LateFeeKind.FLAT,
        amount=Decimal("5.00"),
        apply_after_days=30,
        actor_user_id=user.id,
    )
    await app_session.commit()

    results = await service.apply_late_fees(session=app_session)
    await app_session.commit()
    assert len(results) == 1
    assert results[0].amount == Decimal("5.00")


@pytest.mark.asyncio
async def test_no_policy_no_op(client: AsyncClient, app_session: AsyncSession) -> None:
    await _setup(app_session, client)
    results = await service.apply_late_fees(session=app_session)
    await app_session.commit()
    assert results == []
