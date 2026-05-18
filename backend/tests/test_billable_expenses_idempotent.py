"""A billable source can't be linked to two invoice lines (Phase 8.8, #135).

Once ``billed_invoice_item_id`` is stamped, a second composer attempt
raises ``InvalidInvoiceItemError`` (which wraps the underlying
``InvalidBillableExpenseError`` from the billable_expenses service)."""

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
async def test_same_source_cannot_be_billed_twice(app_session: AsyncSession) -> None:
    actor = await seed_user(app_session, email="owner-idem@example.com")
    customer = await seed_customer(app_session)
    bill_item = await seed_billable_bill_item(
        app_session, actor_user_id=actor.id, customer_id=customer.id
    )

    # First link succeeds.
    await invoices_service.create_draft(
        app_session,
        customer_id=customer.id,
        items=[
            {
                "kind": "manual",
                "description": "",
                "billable_source": {"kind": "bill_item", "id": str(bill_item.id)},
            }
        ],
        actor_user_id=actor.id,
    )
    await app_session.commit()

    # Second link attempt should raise.
    with pytest.raises(invoices_service.InvalidInvoiceItemError):
        await invoices_service.create_draft(
            app_session,
            customer_id=customer.id,
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
