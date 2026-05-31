"""Dashboard KPI tiles tests (Phase 10.6, #181)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.bill import Bill, BillState
from app.models.invoice import Invoice, InvoiceState
from app.services import journal_entries as journal_service
from app.services.reports import dashboard_kpis as kpi_service
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, seed_account, seed_owner


async def _post_je(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    description: str,
    posted_at: datetime,
    lines: list[tuple[uuid.UUID, str, str]],
):
    jls = [
        journal_service.JournalLineInput(
            account_id=acct_id,
            debit=d(dr),
            credit=d(cr),
            line_number=i,
        )
        for i, (acct_id, dr, cr) in enumerate(lines, start=1)
    ]
    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=description,
            posted_at=posted_at,
            lines=jls,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    await session.flush()
    return entry


async def _seed_invoice(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    user_id: uuid.UUID,
    outstanding: str,
    state: InvoiceState,
) -> Invoice:
    inv_id = uuid.uuid4()
    inv = Invoice(
        id=inv_id,
        invoice_number=f"INV-TEST-{inv_id.hex[:8]}",
        customer_id=customer_id,
        subtotal=Decimal(outstanding),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal(outstanding),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal(outstanding),
        state=state,
        created_by_user_id=user_id,
    )
    session.add(inv)
    await session.flush()
    return inv


async def _seed_bill(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    user_id: uuid.UUID,
    outstanding: str,
    state: BillState,
) -> Bill:
    bill_id = uuid.uuid4()
    bill = Bill(
        id=bill_id,
        bill_number=f"BILL-TEST-{bill_id.hex[:8]}",
        vendor_id=vendor_id,
        subtotal=Decimal(outstanding),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal(outstanding),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal(outstanding),
        state=state,
        created_by_user_id=user_id,
    )
    session.add(bill)
    await session.flush()
    return bill


@pytest.mark.asyncio
async def test_aggregates_all_tiles(client: AsyncClient, app_session: AsyncSession) -> None:
    from app.models.customer import Customer
    from app.models.vendor import Vendor

    user = await seed_owner(app_session)
    bank = await seed_account(app_session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(app_session, code="4000", name="Sales", type="revenue")
    await app_session.commit()

    # Cash on hand setting points at the bank account.
    await SettingsService.set(
        "reports.cash_accounts",
        [str(bank.id)],
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    today = datetime.now(UTC)
    # Cash sale → bank +100, net income +100.
    await _post_je(
        app_session,
        actor_user_id=user.id,
        description="Sale",
        posted_at=today,
        lines=[(bank.id, "100.00", "0"), (revenue.id, "0", "100.00")],
    )
    await app_session.commit()

    # Outstanding invoice + overdue invoice.
    customer = Customer(
        id=uuid.uuid4(),
        customer_number="CUST-1",
        display_name="A",
        state="active",
    )
    app_session.add(customer)
    await app_session.commit()
    await _seed_invoice(
        app_session,
        customer_id=customer.id,
        user_id=user.id,
        outstanding="50.00",
        state=InvoiceState.ISSUED,
    )
    await _seed_invoice(
        app_session,
        customer_id=customer.id,
        user_id=user.id,
        outstanding="25.00",
        state=InvoiceState.OVERDUE,
    )
    await app_session.commit()

    vendor = Vendor(
        id=uuid.uuid4(),
        vendor_number="VND-1",
        display_name="V",
        payment_terms_days=30,
        state="active",
    )
    app_session.add(vendor)
    await app_session.commit()
    await _seed_bill(
        app_session,
        vendor_id=vendor.id,
        user_id=user.id,
        outstanding="40.00",
        state=BillState.ISSUED,
    )
    await app_session.commit()

    kpis = await kpi_service.build(app_session)
    assert kpis.cash_on_hand == Decimal("100.00")
    assert kpis.accounts_receivable == Decimal("75.00")  # 50 issued + 25 overdue
    assert kpis.accounts_payable == Decimal("40.00")
    assert kpis.overdue_invoice_count == 1
    assert kpis.overdue_bill_count == 0
    assert kpis.low_stock_alert_count == 0
    assert kpis.net_income_mtd == Decimal("100.00")
    assert kpis.net_income_ytd == Decimal("100.00")
    # Production builds `as_of` from `datetime.now(UTC).date()` — compare
    # against the same source, not local `date.today()`, or this silently
    # fails near midnight UTC when local and UTC are on different days.
    assert kpis.as_of == datetime.now(UTC).date()


@pytest.mark.asyncio
async def test_endpoint_smoke(client: AsyncClient, app_session: AsyncSession) -> None:
    from app.models.auth import Role
    from app.services.auth import create_user

    await create_user(
        app_session,
        email="kpi@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()

    login = await client.post(
        "/api/v1/auth/login", json={"email": "kpi@example.com", "password": "pw-correct"}
    )
    token = login.json()["access_token"]

    resp = await client.get("/api/v1/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "cash_on_hand",
        "accounts_receivable",
        "accounts_payable",
        "overdue_invoice_count",
        "overdue_bill_count",
        "low_stock_alert_count",
        "net_income_mtd",
        "net_income_ytd",
        "last_updated_at",
    ):
        assert key in body
