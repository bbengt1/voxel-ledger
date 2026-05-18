"""Delete blocked when bill_item / recurring_bill_template_item references category.

Phase 8.6, #133.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bills_helpers import (
    sample_bill_body,
    seed_full_ap_stack,
    seed_vendor,
)
from tests._expense_categories_helpers import (
    auth_header,
    seed_expense_account,
    token_for,
)


@pytest.mark.asyncio
async def test_delete_blocked_when_bill_item_references(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    await seed_full_ap_stack(app_session, with_tax=False)
    vendor = await seed_vendor(app_session)
    acct = await seed_expense_account(app_session, code="5300", name="Misc")

    cat_r = await client.post(
        "/api/v1/expense-categories",
        json={"code": "MISC", "name": "Misc", "default_expense_account_id": str(acct.id)},
        headers=auth_header(token),
    )
    cid = cat_r.json()["id"]

    body = sample_bill_body(
        vendor_id=str(vendor.id),
        items=[
            {
                "kind": "expense_category",
                "expense_category_id": cid,
                "description": "Item",
                "quantity": "1",
                "unit_price": "10.00",
            }
        ],
    )
    await client.post("/api/v1/bills", headers=auth_header(token), json=body)

    dr = await client.delete(f"/api/v1/expense-categories/{cid}", headers=auth_header(token))
    assert dr.status_code == 400
    assert "category in use; archive instead" in dr.json()["detail"]

    # Archive still works.
    ar = await client.post(f"/api/v1/expense-categories/{cid}/archive", headers=auth_header(token))
    assert ar.status_code == 200
    assert ar.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_succeeds_with_no_refs(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    acct = await seed_expense_account(app_session)

    cat_r = await client.post(
        "/api/v1/expense-categories",
        json={"code": "LONELY", "name": "Lonely", "default_expense_account_id": str(acct.id)},
        headers=auth_header(token),
    )
    cid = cat_r.json()["id"]

    dr = await client.delete(f"/api/v1/expense-categories/{cid}", headers=auth_header(token))
    assert dr.status_code == 204
