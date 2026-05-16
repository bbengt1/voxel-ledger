"""Overdue marker worker / service (Phase 7.6, #114)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role, User
from app.models.invoice import InvoiceState
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


@pytest.mark.asyncio
async def test_past_due_invoice_transitions_to_overdue(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="100.00"
    )
    # Back-date due_at into the past.
    fresh = await get_invoice(app_session, invoice.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=2)
    await app_session.commit()

    result = await service.mark_overdue(session=app_session)
    await app_session.commit()
    assert invoice.id in result.invoice_ids

    refreshed = await get_invoice(app_session, invoice.id)
    assert refreshed.state == InvoiceState.OVERDUE


@pytest.mark.asyncio
async def test_not_yet_due_invoice_stays_issued(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="100.00"
    )
    # The customer's payment_terms_days default is 30 → due_at is ~30 days
    # out; leave it in the future and verify the marker no-ops.
    result = await service.mark_overdue(session=app_session)
    await app_session.commit()
    assert invoice.id not in result.invoice_ids

    refreshed = await get_invoice(app_session, invoice.id)
    assert refreshed.state == InvoiceState.ISSUED


@pytest.mark.asyncio
async def test_overdue_marker_idempotent(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="100.00"
    )
    fresh = await get_invoice(app_session, invoice.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=2)
    await app_session.commit()

    first = await service.mark_overdue(session=app_session)
    await app_session.commit()
    second = await service.mark_overdue(session=app_session)
    await app_session.commit()

    assert len(first.invoice_ids) == 1
    assert second.invoice_ids == []


@pytest.mark.asyncio
async def test_partially_paid_past_due_also_transitions(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="100.00"
    )
    # Force partially_paid + past-due
    fresh = await get_invoice(app_session, invoice.id)
    fresh.state = InvoiceState.PARTIALLY_PAID
    fresh.due_at = datetime.now(UTC) - timedelta(days=5)
    await app_session.commit()

    result = await service.mark_overdue(session=app_session)
    await app_session.commit()
    assert invoice.id in result.invoice_ids
    refreshed = await get_invoice(app_session, invoice.id)
    assert refreshed.state == InvoiceState.OVERDUE
