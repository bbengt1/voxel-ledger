"""Overdue bill marker worker / service (Phase 8.4, #131)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role, User
from app.models.bill import Bill, BillState
from app.services import bill_overdue as service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bill_payments_helpers import (
    auth_header,  # noqa: F401  (re-exported for parity with AR-side tests)
    seed_full_ap_payments_stack,
    seed_issued_bill,
    seed_vendor,
    token_for,
)


async def _get_bill(session: AsyncSession, bill_id: uuid.UUID) -> Bill:
    return (await session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()


@pytest.mark.asyncio
async def test_past_due_bill_transitions_to_overdue(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )
    # Back-date due_at into the past.
    fresh = await _get_bill(app_session, bill.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=2)
    await app_session.commit()

    result = await service.mark_overdue(session=app_session)
    await app_session.commit()
    assert bill.id in result.bill_ids

    refreshed = await _get_bill(app_session, bill.id)
    assert refreshed.state == BillState.OVERDUE


@pytest.mark.asyncio
async def test_not_yet_due_bill_stays_issued(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )
    # The vendor's payment_terms_days default is 30 → due_at is ~30 days
    # out; leave it in the future and verify the marker no-ops.
    result = await service.mark_overdue(session=app_session)
    await app_session.commit()
    assert bill.id not in result.bill_ids

    refreshed = await _get_bill(app_session, bill.id)
    assert refreshed.state == BillState.ISSUED


@pytest.mark.asyncio
async def test_overdue_bill_marker_idempotent(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )
    fresh = await _get_bill(app_session, bill.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=2)
    await app_session.commit()

    first = await service.mark_overdue(session=app_session)
    await app_session.commit()
    second = await service.mark_overdue(session=app_session)
    await app_session.commit()

    assert len(first.bill_ids) == 1
    assert second.bill_ids == []


@pytest.mark.asyncio
async def test_partially_paid_past_due_bill_also_transitions(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price="100.00"
    )
    # Force partially_paid + past-due
    fresh = await _get_bill(app_session, bill.id)
    fresh.state = BillState.PARTIALLY_PAID
    fresh.due_at = datetime.now(UTC) - timedelta(days=5)
    await app_session.commit()

    result = await service.mark_overdue(session=app_session)
    await app_session.commit()
    assert bill.id in result.bill_ids
    refreshed = await _get_bill(app_session, bill.id)
    assert refreshed.state == BillState.OVERDUE
