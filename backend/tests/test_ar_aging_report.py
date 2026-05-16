"""AR aging report — bucket distribution + CSV (Phase 7.6, #114)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.invoice import Invoice
from app.services.reports import ar_aging
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._late_fees_helpers import (
    get_invoice,
    seed_customer,
    seed_full_ar_stack,
    seed_issued_invoice,
)
from tests._payments_helpers import auth_header, token_for


async def _seed_invoice_with_due(
    app_session: AsyncSession,
    *,
    customer,
    user,
    price: str,
    days_past_due: int,
) -> Invoice:
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price=price
    )
    fresh = await get_invoice(app_session, invoice.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=days_past_due)
    await app_session.commit()
    return invoice


@pytest.mark.asyncio
async def test_aging_distributes_into_default_buckets(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()

    # Four invoices across the four default buckets (0-30, 31-60, 61-90, 91+).
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="10.00", days_past_due=5
    )
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="20.00", days_past_due=45
    )
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="30.00", days_past_due=75
    )
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="40.00", days_past_due=120
    )

    report = await ar_aging.build(app_session)
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
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="100.00", days_past_due=5
    )

    report = await ar_aging.build(app_session)
    csv = ar_aging.to_csv(report)
    lines = csv.strip().splitlines()
    expected = "customer_number,display_name,0-30,31-60,61-90,91+,total_outstanding"
    assert lines[0].startswith(expected)
    assert "GRAND TOTAL" in lines[-1]


@pytest.mark.asyncio
async def test_aging_endpoint_returns_buckets(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="50.00", days_past_due=10
    )

    r = await client.get("/api/v1/reports/ar-aging", headers=auth_header(owner))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bucket_labels"] == ["0-30", "31-60", "61-90", "91+"]
    assert body["grand_total"] == "50.000000"


@pytest.mark.asyncio
async def test_aging_endpoint_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="50.00", days_past_due=10
    )

    r = await client.get("/api/v1/reports/ar-aging?format=csv", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "GRAND TOTAL" in r.text


@pytest.mark.asyncio
async def test_aging_endpoint_custom_buckets_query_param(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    await _seed_invoice_with_due(
        app_session, customer=customer, user=user, price="50.00", days_past_due=10
    )

    r = await client.get(
        "/api/v1/reports/ar-aging?buckets=15,45",
        headers=auth_header(owner),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bucket_labels"] == ["0-15", "16-45", "46+"]
