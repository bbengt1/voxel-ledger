"""Voiding an invoice reverses the posted JE (Phase 7.3, #111)."""

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

from tests._invoices_helpers import (
    auth_header,
    sample_invoice_body,
    seed_ar_posting_defaults,
    seed_customer,
    token_for,
)


@pytest.mark.asyncio
async def test_void_reverses_je_net_zero(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    customer = await seed_customer(app_session)

    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(
            customer_id=str(customer.id),
            tax_amount="1.00",
        ),
    )
    invoice_id = create.json()["id"]
    issued = await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))
    original_je_id = uuid.UUID(issued.json()["posting_journal_entry_id"])

    void = await client.post(f"/api/v1/invoices/{invoice_id}/void", headers=auth_header(owner))
    assert void.status_code == 200, void.text
    assert void.json()["state"] == "void"

    # Verify a new reversing entry exists referencing the original.
    original_je = (
        await app_session.execute(select(JournalEntry).where(JournalEntry.id == original_je_id))
    ).scalar_one()
    assert original_je.is_reversed is True

    reversing = (
        await app_session.execute(
            select(JournalEntry).where(JournalEntry.reversal_of_entry_id == original_je_id)
        )
    ).scalar_one()
    # Net zero: combined debits of original + reversing == combined credits.
    all_lines = (
        (
            await app_session.execute(
                select(JournalLine).where(JournalLine.entry_id.in_([original_je.id, reversing.id]))
            )
        )
        .scalars()
        .all()
    )
    total_d = sum(line.debit for line in all_lines)
    total_c = sum(line.credit for line in all_lines)
    assert total_d == total_c
    # Specifically, debits across all lines on the original should equal
    # credits across the reversing entry for the same account.
    by_account_d_o = {}
    by_account_c_r = {}
    for line in all_lines:
        if line.entry_id == original_je.id:
            by_account_d_o.setdefault(line.account_id, Decimal("0"))
            by_account_d_o[line.account_id] += line.debit - line.credit
        else:
            by_account_c_r.setdefault(line.account_id, Decimal("0"))
            by_account_c_r[line.account_id] += line.debit - line.credit
    for acct_id, net in by_account_d_o.items():
        assert by_account_c_r[acct_id] == -net, f"account {acct_id} not net zero"


@pytest.mark.asyncio
async def test_void_blocked_when_payments_applied(
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

    # Manually mark a payment applied (Phase 7.4 will own this; for now
    # we mutate the row to simulate the state).
    invoice = (
        await app_session.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
    ).scalar_one()
    invoice.amount_paid = Decimal("5.00")
    await app_session.commit()

    void = await client.post(f"/api/v1/invoices/{invoice_id}/void", headers=auth_header(owner))
    assert void.status_code == 400
    assert "applied payments" in void.json()["detail"]
    assert "Phase 7.4" in void.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_void_paid_invoice(client: AsyncClient, app_session: AsyncSession) -> None:
    """Paid invoices cannot be voided (issue a credit memo instead)."""
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

    # Force state to paid for the test (Phase 7.4 owns the legitimate path).
    from app.models.invoice import InvoiceState

    invoice = (
        await app_session.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
    ).scalar_one()
    invoice.state = InvoiceState.PAID
    await app_session.commit()

    void = await client.post(f"/api/v1/invoices/{invoice_id}/void", headers=auth_header(owner))
    assert void.status_code == 400
