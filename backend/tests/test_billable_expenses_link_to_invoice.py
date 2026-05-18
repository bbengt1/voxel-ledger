"""Invoice composer accepts a per-line ``billable_source`` reference,
applies the markup, stamps the source's ``billed_invoice_item_id``, and
emits ``ap.BillableExpenseLinked`` (Phase 8.8, #135)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.events.types import ap as ap_events
from app.models.bill import BillItem
from app.models.event import Event
from app.services import invoices as invoices_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._billable_expenses_helpers import (
    seed_billable_bill_item,
    seed_billable_expense_claim_line,
    seed_customer,
)
from tests._expense_claims_helpers import seed_user


@pytest.mark.asyncio
async def test_billable_bill_item_appended_to_invoice(
    app_session: AsyncSession,
) -> None:
    actor = await seed_user(app_session, email="owner-link@example.com")
    customer = await seed_customer(app_session)

    bill_item = await seed_billable_bill_item(
        app_session,
        actor_user_id=actor.id,
        customer_id=customer.id,
        amount="100.00",
        markup_percent="10",
    )

    invoice = await invoices_service.create_draft(
        app_session,
        customer_id=customer.id,
        items=[
            {
                "kind": "manual",
                "description": "",  # composer fills from source
                "billable_source": {"kind": "bill_item", "id": str(bill_item.id)},
            }
        ],
        actor_user_id=actor.id,
    )
    await app_session.commit()

    # The composer added a line with the marked-up amount.
    assert len(invoice.items) == 1
    line = invoice.items[0]
    assert line.extended_amount == Decimal("110.000000")
    assert "Subcontractor" in line.description

    # The source bill_item is stamped with the new invoice_item id.
    fresh = (
        await app_session.execute(select(BillItem).where(BillItem.id == bill_item.id))
    ).scalar_one()
    assert fresh.billed_invoice_item_id == line.id

    # And an ap.BillableExpenseLinked event landed.
    events = (
        (
            await app_session.execute(
                select(Event).where(Event.type == ap_events.TYPE_BILLABLE_EXPENSE_LINKED)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    payload = events[0].payload
    assert payload["source_kind"] == "bill_item"
    assert payload["source_id"] == str(bill_item.id)
    assert payload["invoice_item_id"] == str(line.id)
    assert Decimal(payload["amount"]) == Decimal("110.000000")
    assert Decimal(payload["source_amount"]) == Decimal("100.000000")


@pytest.mark.asyncio
async def test_billable_expense_claim_line_appended_to_invoice(
    app_session: AsyncSession,
) -> None:
    actor = await seed_user(app_session, email="owner-link-c@example.com")
    customer = await seed_customer(app_session)

    line_src = await seed_billable_expense_claim_line(
        app_session,
        submitter_user_id=actor.id,
        customer_id=customer.id,
        amount="60.00",
        markup_percent="15",
    )

    invoice = await invoices_service.create_draft(
        app_session,
        customer_id=customer.id,
        items=[
            {
                "kind": "manual",
                "description": "",
                "billable_source": {
                    "kind": "expense_claim_line",
                    "id": str(line_src.id),
                },
            }
        ],
        actor_user_id=actor.id,
    )
    await app_session.commit()

    line = invoice.items[0]
    # 60 * 1.15 = 69.
    assert line.extended_amount == Decimal("69.000000")
