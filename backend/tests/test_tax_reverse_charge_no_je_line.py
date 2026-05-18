"""Reverse-charge: no Cr line in JE, event carries would-be amount (Phase 9.5)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.events.types import ar as ar_events
from app.models.auth import Role
from app.models.customer import Customer
from app.models.event import Event
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
async def test_reverse_charge_no_cr_line_event_carries_amount(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_ar_posting_defaults(app_session, with_tax=False)
    liability_acct = await seed_liability_account(app_session)
    await app_session.commit()

    profile = await seed_tax_profile(
        app_session,
        code="EU-RC",
        name="EU Reverse Charge",
        jurisdiction="EU",
        is_reverse_charge=True,
        rates=[("VAT", Decimal("0.20"), liability_acct.id, False)],
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
                "description": "Service",
                "quantity": "1",
                "unit_price": "100.00",
            }
        ],
    )
    create = await client.post("/api/v1/invoices", headers=auth_header(owner), json=body)
    assert create.status_code == 201, create.text
    invoice_id = create.json()["id"]
    # Line tax stored as zero (reverse-charge memo only)
    assert create.json()["tax_amount"] == "0.000000"

    issued = await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    je_id = uuid.UUID(issued.json()["posting_journal_entry_id"])

    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == je_id)
        .options(selectinload(JournalEntry.lines))
    )
    je = (await app_session.execute(stmt)).scalar_one()
    # No line should reference the liability account
    account_ids = {line.account_id for line in je.lines}
    assert liability_acct.id not in account_ids
    # AR Dr is just the subtotal
    assert je.lines[0] is not None
    by_account = {line.account_id: line for line in je.lines}
    assert by_account[accounts["ar_account_id"]].debit == Decimal("100.000000")

    # Event payload carries the would-be reverse-charge amount
    ev_stmt = select(Event).where(Event.type == ar_events.TYPE_INVOICE_ISSUED)
    issued_events = list((await app_session.execute(ev_stmt)).scalars().all())
    assert len(issued_events) == 1
    rc = issued_events[0].payload.get("reverse_charge_tax") or {}
    assert rc
    # Total reverse-charge sums to 20% of 100
    total = sum(Decimal(v) for v in rc.values())
    assert total == Decimal("20.000000")
