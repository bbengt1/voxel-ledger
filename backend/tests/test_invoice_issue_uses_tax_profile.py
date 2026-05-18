"""Invoice issue uses per-rate Cr lines from tax profile (Phase 9.5, #157)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.customer import Customer
from app.models.journal_entry import JournalEntry
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tests._invoices_helpers import (
    auth_header,
    sample_invoice_body,
    seed_ar_posting_defaults,
    seed_customer,
    token_for,
)
from tests._tax_helpers import seed_liability_account, seed_tax_profile


@pytest.mark.asyncio
async def test_invoice_issue_posts_per_rate_credits(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_ar_posting_defaults(app_session, with_tax=False)
    gst_acct = await seed_liability_account(app_session, code="2210", name="GST Payable")
    pst_acct = await seed_liability_account(app_session, code="2220", name="PST Payable")
    await app_session.commit()
    profile = await seed_tax_profile(
        app_session,
        code="CA-COMBINED",
        name="GST+PST",
        jurisdiction="CA",
        rates=[
            ("GST", Decimal("0.05"), gst_acct.id, False),
            ("PST", Decimal("0.08"), pst_acct.id, True),
        ],
    )

    customer = await seed_customer(app_session)
    customer_row = (
        await app_session.execute(select(Customer).where(Customer.id == customer.id))
    ).scalar_one()
    customer_row.tax_profile_id = profile.id
    await app_session.commit()

    body = sample_invoice_body(
        customer_id=str(customer.id),
        items=[
            {
                "kind": "manual",
                "description": "Widget",
                "quantity": "1",
                "unit_price": "100.00",
            }
        ],
    )
    create = await client.post("/api/v1/invoices", headers=auth_header(owner), json=body)
    assert create.status_code == 201, create.text
    invoice_id = create.json()["id"]
    # Total should reflect 5 + 8.40 = 13.40 tax on $100 subtotal
    assert create.json()["tax_amount"] == "13.400000"

    issued = await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    je_id = uuid.UUID(issued.json()["posting_journal_entry_id"])

    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == je_id)
        .options(selectinload(JournalEntry.lines))
    )
    je = (await app_session.execute(stmt)).scalar_one()
    by_account = {line.account_id: line for line in je.lines}
    assert by_account[gst_acct.id].credit == Decimal("5.000000")
    assert by_account[pst_acct.id].credit == Decimal("8.400000")
    assert by_account[accounts["ar_account_id"]].debit == Decimal("113.400000")
    assert by_account[accounts["revenue_account_id"]].credit == Decimal("100.000000")
