"""Invoice void guards (Phase 7.3, #111).

QBO is the sole ledger (epic #312, Phase 5e): the void-side GL effect
is an outbox reverse row, covered in test_quickbooks_invoice_sync.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.models.invoice import Invoice
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
