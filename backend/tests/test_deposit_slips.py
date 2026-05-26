"""Undeposited funds + deposit slip tests (Parity #235)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.account import Account
from app.models.auth import Role
from app.models.deposit_slip import DepositSlip, DepositSlipItem, DepositSlipState
from app.models.event import Event
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


async def _seed_undeposited_account(session: AsyncSession) -> Account:
    acct = Account(
        id=uuid.uuid4(), code="1101", name="Undeposited funds", type="asset"
    )
    session.add(acct)
    await session.flush()
    await SettingsService.set(
        "ar.undeposited_funds_account_id",
        acct.id,
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    return acct


async def _seed_bank_account(session: AsyncSession) -> Account:
    acct = Account(id=uuid.uuid4(), code="1000", name="Bank", type="asset")
    session.add(acct)
    await session.flush()
    await SettingsService.set(
        "ar.default_bank_account_id",
        acct.id,
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    return acct


async def _issue_invoice_and_create_payment(
    client: AsyncClient,
    *,
    token: str,
    customer_id: str,
    amount: str,
    deposit_to_undeposited: bool,
) -> tuple[str, str]:
    """Issue an invoice + create + apply a payment. Returns
    ``(payment_id, invoice_id)``."""
    invoice = await client.post(
        "/api/v1/invoices",
        headers=auth_header(token),
        json=sample_invoice_body(
            customer_id=customer_id,
            tax_amount="0",
            items=[
                {
                    "kind": "manual",
                    "description": "Widget",
                    "quantity": "1",
                    "unit_price": amount,
                }
            ],
        ),
    )
    invoice_id = invoice.json()["id"]
    await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(token))

    payment = await client.post(
        "/api/v1/payments",
        headers=auth_header(token),
        json={
            "customer_id": customer_id,
            "amount": amount,
            "method": "check",
            "deposit_to_undeposited": deposit_to_undeposited,
        },
    )
    assert payment.status_code == 201, payment.text
    payment_id = payment.json()["id"]
    await client.post(
        f"/api/v1/payments/{payment_id}/apply",
        headers=auth_header(token),
        json={"applications": [{"invoice_id": invoice_id, "amount": amount}]},
    )
    return payment_id, invoice_id


@pytest.mark.asyncio
async def test_payment_with_flag_debits_undeposited(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """The apply-payment JE debits the undeposited account when the
    payment carries ``deposit_to_undeposited=True``."""
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    bank = await _seed_bank_account(app_session)
    undeposited = await _seed_undeposited_account(app_session)
    customer = await seed_customer(app_session)

    payment_id, _ = await _issue_invoice_and_create_payment(
        client,
        token=owner,
        customer_id=str(customer.id),
        amount="100.00",
        deposit_to_undeposited=True,
    )

    # The apply-payment JE should have one debit on the undeposited
    # account, NOT the bank account.
    lines = (
        await app_session.execute(select(JournalLine))
    ).scalars().all()
    debits_on_undeposited = sum(
        ln.debit for ln in lines if ln.account_id == undeposited.id
    )
    debits_on_bank = sum(
        ln.debit for ln in lines if ln.account_id == bank.id
    )
    assert debits_on_undeposited >= Decimal("100.000000")
    assert debits_on_bank == Decimal("0")
    _ = payment_id


@pytest.mark.asyncio
async def test_build_slip_consolidates_payments(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Three undeposited payments → one slip; the slip JE has one
    debit on the bank account for the consolidated total."""
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    bank = await _seed_bank_account(app_session)
    undeposited = await _seed_undeposited_account(app_session)
    customer = await seed_customer(app_session)

    payment_ids = []
    for amt in ("50.00", "75.00", "25.00"):
        pid, _ = await _issue_invoice_and_create_payment(
            client,
            token=owner,
            customer_id=str(customer.id),
            amount=amt,
            deposit_to_undeposited=True,
        )
        payment_ids.append(pid)

    resp = await client.post(
        "/api/v1/deposit-slips",
        headers=auth_header(owner),
        json={
            "payment_ids": payment_ids,
            "bank_account_id": str(bank.id),
            "deposit_date": datetime.now(UTC).date().isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert Decimal(body["total_amount"]) == Decimal("150.000000")
    assert body["state"] == DepositSlipState.DEPOSITED.value
    slip_id = uuid.UUID(body["id"])

    # The slip's posting JE has exactly two lines: DR bank, CR undeposited.
    slip = (
        await app_session.execute(select(DepositSlip).where(DepositSlip.id == slip_id))
    ).scalar_one()
    je_id = slip.posting_journal_entry_id
    assert je_id is not None
    slip_lines = (
        await app_session.execute(
            select(JournalLine).where(JournalLine.entry_id == je_id)
        )
    ).scalars().all()
    by_account = {ln.account_id: ln for ln in slip_lines}
    assert by_account[bank.id].debit == Decimal("150.000000")
    assert by_account[bank.id].credit == Decimal("0")
    assert by_account[undeposited.id].debit == Decimal("0")
    assert by_account[undeposited.id].credit == Decimal("150.000000")

    # Slip items recorded per payment.
    items = (
        await app_session.execute(
            select(DepositSlipItem).where(DepositSlipItem.deposit_slip_id == slip_id)
        )
    ).scalars().all()
    assert len(items) == 3

    # Audit event recorded.
    evt = (
        await app_session.execute(
            select(Event).where(Event.type == "ar.DepositSlipBuilt")
        )
    ).scalar_one()
    assert evt.payload["slip_number"] == body["slip_number"]
    assert Decimal(evt.payload["total"]) == Decimal("150.000000")


@pytest.mark.asyncio
async def test_cannot_re_add_payment_to_a_second_slip(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    bank = await _seed_bank_account(app_session)
    await _seed_undeposited_account(app_session)
    customer = await seed_customer(app_session)

    pid, _ = await _issue_invoice_and_create_payment(
        client,
        token=owner,
        customer_id=str(customer.id),
        amount="42.00",
        deposit_to_undeposited=True,
    )
    body = {
        "payment_ids": [pid],
        "bank_account_id": str(bank.id),
        "deposit_date": datetime.now(UTC).date().isoformat(),
    }
    first = await client.post(
        "/api/v1/deposit-slips", headers=auth_header(owner), json=body
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/deposit-slips", headers=auth_header(owner), json=body
    )
    assert second.status_code == 400
    assert "already on a deposit slip" in second.text


@pytest.mark.asyncio
async def test_payment_without_flag_does_not_show_as_undeposited(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_ar_posting_defaults(app_session)
    await _seed_bank_account(app_session)
    await _seed_undeposited_account(app_session)
    customer = await seed_customer(app_session)

    # Two payments: one flagged, one not.
    flagged, _ = await _issue_invoice_and_create_payment(
        client,
        token=owner,
        customer_id=str(customer.id),
        amount="10.00",
        deposit_to_undeposited=True,
    )
    not_flagged, _ = await _issue_invoice_and_create_payment(
        client,
        token=owner,
        customer_id=str(customer.id),
        amount="20.00",
        deposit_to_undeposited=False,
    )

    resp = await client.get(
        "/api/v1/deposit-slips/undeposited", headers=auth_header(owner)
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert flagged in ids
    assert not_flagged not in ids
