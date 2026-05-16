"""Issuing an invoice posts AR/Revenue/Tax JE in the same TX (Phase 7.3, #111)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.invoice import Invoice
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
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
async def test_issue_posts_ar_revenue_tax_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_ar_posting_defaults(app_session, with_tax=True)
    customer = await seed_customer(app_session)

    body = sample_invoice_body(
        customer_id=str(customer.id),
        tax_amount="2.50",
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
    payload = issued.json()
    assert payload["state"] == "issued"
    assert payload["issued_at"] is not None
    assert payload["due_at"] is not None
    je_id = uuid.UUID(payload["posting_journal_entry_id"])
    assert je_id is not None

    # Verify JE structure
    stmt = (
        select(JournalEntry)
        .where(JournalEntry.id == je_id)
        .options(selectinload(JournalEntry.lines))
    )
    je = (await app_session.execute(stmt)).scalar_one()
    lines = sorted(je.lines, key=lambda line: line.line_number)

    by_account = {line.account_id: line for line in lines}
    ar_line = by_account[accounts["ar_account_id"]]
    revenue_line = by_account[accounts["revenue_account_id"]]
    tax_line = by_account[accounts["tax_account_id"]]

    assert ar_line.debit == Decimal("102.500000")
    assert ar_line.credit == Decimal("0")
    assert revenue_line.credit == Decimal("100.000000")
    assert revenue_line.debit == Decimal("0")
    assert tax_line.credit == Decimal("2.500000")
    assert tax_line.debit == Decimal("0")

    # Sum balanced
    total_d = sum(line.debit for line in lines)
    total_c = sum(line.credit for line in lines)
    assert total_d == total_c


@pytest.mark.asyncio
async def test_issue_without_tax_omits_tax_line(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    accounts = await seed_ar_posting_defaults(app_session, with_tax=False)
    customer = await seed_customer(app_session)

    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    invoice_id = create.json()["id"]

    issued = await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))
    assert issued.status_code == 200, issued.text
    je_id = uuid.UUID(issued.json()["posting_journal_entry_id"])
    stmt = select(JournalLine).where(JournalLine.entry_id == je_id)
    rows = list((await app_session.execute(stmt)).scalars().all())
    assert len(rows) == 2
    account_ids = {r.account_id for r in rows}
    assert accounts["ar_account_id"] in account_ids
    assert accounts["revenue_account_id"] in account_ids


@pytest.mark.asyncio
async def test_invoice_posting_je_fk_persisted(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    customer = await seed_customer(app_session)

    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    invoice_id = create.json()["id"]
    await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))

    invoice = (
        await app_session.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
    ).scalar_one()
    assert invoice.posting_journal_entry_id is not None
