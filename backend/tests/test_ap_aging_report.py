"""AP aging report — bucket distribution + CSV (Phase 8.4, #131)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.bill import Bill
from app.services.reports import ap_aging
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bill_payments_helpers import (
    auth_header,
    seed_full_ap_payments_stack,
    seed_issued_bill,
    seed_vendor,
    token_for,
)


async def _get_bill(session: AsyncSession, bill_id: uuid.UUID) -> Bill:
    return (await session.execute(select(Bill).where(Bill.id == bill_id))).scalar_one()


async def _seed_bill_with_due(
    app_session: AsyncSession,
    *,
    vendor,
    user,
    price: str,
    days_past_due: int,
) -> Bill:
    bill = await seed_issued_bill(
        app_session, vendor=vendor, actor_user_id=user.id, unit_price=price
    )
    fresh = await _get_bill(app_session, bill.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=days_past_due)
    await app_session.commit()
    return bill


@pytest.mark.asyncio
async def test_aging_distributes_into_default_buckets(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()

    # Four bills across the four default buckets (0-30, 31-60, 61-90, 91+).
    await _seed_bill_with_due(app_session, vendor=vendor, user=user, price="10.00", days_past_due=5)
    await _seed_bill_with_due(
        app_session, vendor=vendor, user=user, price="20.00", days_past_due=45
    )
    await _seed_bill_with_due(
        app_session, vendor=vendor, user=user, price="30.00", days_past_due=75
    )
    await _seed_bill_with_due(
        app_session, vendor=vendor, user=user, price="40.00", days_past_due=120
    )

    report = await ap_aging.build(app_session)
    assert report.bucket_labels == ["0-30", "31-60", "61-90", "91+"]
    assert len(report.rows) == 1
    row = report.rows[0]
    amounts = [b.amount for b in row.buckets]
    assert amounts == [
        Decimal("10.000000"),
        Decimal("20.000000"),
        Decimal("30.000000"),
        Decimal("40.000000"),
    ]
    assert row.total_outstanding == Decimal("100.000000")
    assert report.grand_total == Decimal("100.000000")


@pytest.mark.asyncio
async def test_aging_csv_has_header_and_grand_total(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_bill_with_due(
        app_session, vendor=vendor, user=user, price="100.00", days_past_due=5
    )

    report = await ap_aging.build(app_session)
    csv = ap_aging.to_csv(report)
    lines = csv.strip().splitlines()
    expected = "vendor_number,display_name,0-30,31-60,61-90,91+,total_outstanding"
    assert lines[0].startswith(expected)
    assert "GRAND TOTAL" in lines[-1]


@pytest.mark.asyncio
async def test_aging_endpoint_returns_buckets(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_bill_with_due(
        app_session, vendor=vendor, user=user, price="50.00", days_past_due=10
    )

    r = await client.get("/api/v1/reports/ap-aging", headers=auth_header(owner))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bucket_labels"] == ["0-30", "31-60", "61-90", "91+"]
    assert body["grand_total"] == "50.000000"


@pytest.mark.asyncio
async def test_aging_endpoint_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_bill_with_due(
        app_session, vendor=vendor, user=user, price="50.00", days_past_due=10
    )

    r = await client.get("/api/v1/reports/ap-aging?format=csv", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "GRAND TOTAL" in r.text


@pytest.mark.asyncio
async def test_aging_endpoint_custom_buckets_query_param(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_payments_stack(app_session)
    vendor = await seed_vendor(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_bill_with_due(
        app_session, vendor=vendor, user=user, price="50.00", days_past_due=10
    )

    r = await client.get(
        "/api/v1/reports/ap-aging?buckets=15,45",
        headers=auth_header(owner),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bucket_labels"] == ["0-15", "16-45", "46+"]
