"""Clear error when AR posting settings unset (Phase 7.3, #111)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import (
    auth_header,
    sample_invoice_body,
    seed_customer,
    token_for,
)


@pytest.mark.asyncio
async def test_issue_without_settings_returns_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    customer = await seed_customer(app_session)
    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    invoice_id = create.json()["id"]

    # No ar.default_* / sales_posting.default_ar_account_id set.
    r = await client.post(f"/api/v1/invoices/{invoice_id}/issue", headers=auth_header(owner))
    assert r.status_code == 400
    assert "configure default AR posting accounts" in r.json()["detail"]
