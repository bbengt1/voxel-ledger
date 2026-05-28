"""Invoice write-off tests (Parity #236)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.account import Account
from app.models.auth import Role
from app.models.event import Event
from app.models.invoice import InvoiceState
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services.settings.service import SettingsService
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


async def _seed_bad_debt_account(session: AsyncSession) -> Account:
    """Add a bad-debt expense account + the setting that points at it."""
    acct = Account(id=uuid.uuid4(), code="6900", name="Bad Debt Expense", type="expense")
    session.add(acct)
    await session.flush()
    await SettingsService.set(
        "ar.default_bad_debt_account_id",
        acct.id,
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    return acct


@pytest.mark.asyncio
async def test_write_off_zeroes_outstanding_and_posts_bad_debt_je(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Happy path: issue + write off → outstanding=0, JE balances,
    state=written_off, ar.InvoiceWrittenOff emitted."""
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    bad_debt = await _seed_bad_debt_account(app_session)
    customer = await seed_customer(app_session)

    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id), tax_amount="0"),
    )
    invoice_id = create.json()["id"]
    await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))

    write_off = await client.post(
        f"/api/v1/invoices/{invoice_id}/write-off",
        headers=auth_header(owner),
        json={"reason": "customer bankrupt"},
    )
    assert write_off.status_code == 200, write_off.text
    body = write_off.json()
    assert body["state"] == InvoiceState.WRITTEN_OFF.value
    assert Decimal(body["amount_outstanding"]) == Decimal("0")

    # JE landed: one DR on bad-debt for the outstanding, one CR on AR.
    write_off_je = (
        (
            await app_session.execute(
                select(JournalEntry).where(JournalEntry.description.like("Write-off of invoice%"))
            )
        )
        .scalars()
        .one()
    )
    lines = (
        (
            await app_session.execute(
                select(JournalLine).where(JournalLine.entry_id == write_off_je.id)
            )
        )
        .scalars()
        .all()
    )
    by_account = {ln.account_id: ln for ln in lines}
    bad_debt_line = by_account[bad_debt.id]
    assert bad_debt_line.debit > 0 and bad_debt_line.credit == 0
    # AR side credits the same amount.
    total_dr = sum(ln.debit for ln in lines)
    total_cr = sum(ln.credit for ln in lines)
    assert total_dr == total_cr

    # Event emitted with the right payload + audit excerpt keys.
    written = (
        (await app_session.execute(select(Event).where(Event.type == "ar.InvoiceWrittenOff")))
        .scalars()
        .one()
    )
    assert written.payload["invoice_id"] == invoice_id
    assert written.payload["bad_debt_account_id"] == str(bad_debt.id)
    assert written.payload["journal_entry_id"] == str(write_off_je.id)
    # reason is in the payload (so replay can reconstruct) but NOT in
    # the audit excerpt (verified at projection-registration time, but
    # spot-check that the payload carries it intentionally).
    assert written.payload["reason"] == "customer bankrupt"


@pytest.mark.asyncio
async def test_cannot_write_off_paid_invoice(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    await _seed_bad_debt_account(app_session)
    customer = await seed_customer(app_session)

    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id), tax_amount="0"),
    )
    invoice_id = create.json()["id"]
    await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))

    # Force into a state where write-off is illegal by setting paid
    # directly on the row (avoids needing the full payment flow).
    from app.models.invoice import Invoice

    inv = (
        await app_session.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
    ).scalar_one()
    inv.state = InvoiceState.PAID
    inv.amount_outstanding = Decimal("0")
    await app_session.commit()

    resp = await client.post(
        f"/api/v1/invoices/{invoice_id}/write-off",
        headers=auth_header(owner),
        json={},
    )
    assert resp.status_code == 400
    assert "transition" in resp.text.lower() or "paid" in resp.text.lower()


@pytest.mark.asyncio
async def test_write_off_role_matrix(client: AsyncClient, app_session: AsyncSession) -> None:
    """Sales role cannot write off."""
    owner = await token_for(Role.OWNER, client, app_session)
    sales = await token_for(Role.SALES, client, app_session)
    await seed_ar_posting_defaults(app_session)
    await _seed_bad_debt_account(app_session)
    customer = await seed_customer(app_session)

    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id), tax_amount="0"),
    )
    invoice_id = create.json()["id"]
    await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))

    resp = await client.post(
        f"/api/v1/invoices/{invoice_id}/write-off",
        headers=auth_header(sales),
        json={},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_write_off_uses_setting_when_account_not_passed(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """When the request body omits ``bad_debt_account_id`` the service
    falls back to ``ar.default_bad_debt_account_id``."""
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    bad_debt = await _seed_bad_debt_account(app_session)
    customer = await seed_customer(app_session)

    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id), tax_amount="0"),
    )
    invoice_id = create.json()["id"]
    await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))

    resp = await client.post(
        f"/api/v1/invoices/{invoice_id}/write-off",
        headers=auth_header(owner),
        json={},
    )
    assert resp.status_code == 200
    written = (
        (await app_session.execute(select(Event).where(Event.type == "ar.InvoiceWrittenOff")))
        .scalars()
        .one()
    )
    assert written.payload["bad_debt_account_id"] == str(bad_debt.id)
