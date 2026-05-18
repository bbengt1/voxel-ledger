"""Legacy fallback: no profile + flat tax_amount + setting (Phase 9.5, #157)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
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


@pytest.mark.asyncio
async def test_no_profile_falls_back_to_setting(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_ar_posting_defaults(app_session, with_tax=True)
    customer = await seed_customer(app_session)

    body = sample_invoice_body(
        customer_id=str(customer.id),
        tax_amount="3.00",
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
    # The setting-based tax payable account should carry the credit.
    assert by_account[accounts["tax_account_id"]].credit == Decimal("3.000000")
