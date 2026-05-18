"""Composer rejects a billable source whose customer doesn't match the
invoice's customer (Phase 8.8, #135)."""

from __future__ import annotations

import pytest
from app.services import invoices as invoices_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._billable_expenses_helpers import (
    seed_billable_bill_item,
    seed_customer,
)
from tests._expense_claims_helpers import seed_user


@pytest.mark.asyncio
async def test_wrong_customer_rejected(app_session: AsyncSession) -> None:
    actor = await seed_user(app_session, email="owner-cf@example.com")
    customer_a = await seed_customer(app_session, display_name="A Co")
    customer_b = await seed_customer(app_session, display_name="B Co")

    bill_item = await seed_billable_bill_item(
        app_session, actor_user_id=actor.id, customer_id=customer_a.id
    )

    with pytest.raises(invoices_service.InvalidInvoiceItemError):
        await invoices_service.create_draft(
            app_session,
            customer_id=customer_b.id,  # mismatch
            items=[
                {
                    "kind": "manual",
                    "description": "",
                    "billable_source": {
                        "kind": "bill_item",
                        "id": str(bill_item.id),
                    },
                }
            ],
            actor_user_id=actor.id,
        )
    await app_session.rollback()
