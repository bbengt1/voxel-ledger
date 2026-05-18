"""Markup math: 10% on $100 = $110; per-line override beats source default
(Phase 8.8, #135)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.services import billable_expenses as billable_service
from app.services import invoices as invoices_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._billable_expenses_helpers import (
    seed_billable_bill_item,
    seed_customer,
)
from tests._expense_claims_helpers import seed_user


def test_compute_billed_amount_pure() -> None:
    assert billable_service.compute_billed_amount(
        source_amount=Decimal("100"), markup_percent=Decimal("10")
    ) == Decimal("110.000000")
    assert billable_service.compute_billed_amount(
        source_amount=Decimal("0"), markup_percent=Decimal("50")
    ) == Decimal("0.000000")
    assert billable_service.compute_billed_amount(
        source_amount=Decimal("33.33"), markup_percent=Decimal("0")
    ) == Decimal("33.330000")


@pytest.mark.asyncio
async def test_markup_defaults_to_source(app_session: AsyncSession) -> None:
    actor = await seed_user(app_session, email="owner-mu1@example.com")
    customer = await seed_customer(app_session)
    bill_item = await seed_billable_bill_item(
        app_session,
        actor_user_id=actor.id,
        customer_id=customer.id,
        amount="200.00",
        markup_percent="25",
    )

    invoice = await invoices_service.create_draft(
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
    # 200 * 1.25 = 250.
    assert invoice.items[0].extended_amount == Decimal("250.000000")


@pytest.mark.asyncio
async def test_markup_override_wins(app_session: AsyncSession) -> None:
    actor = await seed_user(app_session, email="owner-mu2@example.com")
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
                "description": "",
                "billable_source": {
                    "kind": "bill_item",
                    "id": str(bill_item.id),
                    "markup_percent_override": "50",
                },
            }
        ],
        actor_user_id=actor.id,
    )
    await app_session.commit()
    # 100 * 1.50 = 150 (override beats source's 10%).
    assert invoice.items[0].extended_amount == Decimal("150.000000")
