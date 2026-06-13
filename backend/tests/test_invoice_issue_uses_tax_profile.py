"""Invoice issue recomputes per-rate tax from the tax profile (Phase 9.5, #157).

QBO is the sole ledger (epic #312, Phase 5e): the per-rate totals are
aggregated into ``invoice.tax_amount`` and carried on the QBO outbox
spec instead of per-rate local JE credit lines.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.customer import Customer
from app.models.qbo_sync_outbox import QboSyncOutbox
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    await seed_ar_posting_defaults(app_session, with_tax=False)
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
    payload = issued.json()
    # QBO is the sole ledger: no local JE.
    assert payload["posting_journal_entry_id"] is None
    assert payload["tax_amount"] == "13.400000"
    assert payload["total_amount"] == "113.400000"

    # The aggregated tax rides the QBO outbox spec.
    outbox = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "invoice",
                QboSyncOutbox.local_id == uuid.UUID(invoice_id),
            )
        )
    ).scalar_one()
    assert outbox.op == "post"
    assert Decimal(outbox.payload["tax_amount"]) == Decimal("13.400000")
