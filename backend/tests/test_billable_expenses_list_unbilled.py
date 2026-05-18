"""``list_unbilled`` returns billable, unbilled rows for the given customer
(Phase 8.8, #135)."""

from __future__ import annotations

import pytest
from app.services import billable_expenses as billable_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._billable_expenses_helpers import (
    seed_billable_bill_item,
    seed_billable_expense_claim_line,
    seed_customer,
)
from tests._expense_claims_helpers import seed_user


@pytest.mark.asyncio
async def test_list_returns_billable_rows_for_customer(app_session: AsyncSession) -> None:
    actor = await seed_user(app_session, email="owner-billable@example.com")
    customer = await seed_customer(app_session)

    bill_item = await seed_billable_bill_item(
        app_session, actor_user_id=actor.id, customer_id=customer.id
    )
    claim_line = await seed_billable_expense_claim_line(
        app_session, submitter_user_id=actor.id, customer_id=customer.id
    )

    rows = await billable_service.list_unbilled(app_session, customer_id=customer.id)
    assert len(rows) == 2

    kinds = {r.source_kind for r in rows}
    assert kinds == {"bill_item", "expense_claim_line"}

    ids = {r.source_id for r in rows}
    assert bill_item.id in ids
    assert claim_line.id in ids


@pytest.mark.asyncio
async def test_list_excludes_already_billed_rows(app_session: AsyncSession) -> None:
    """Setting ``billed_invoice_item_id`` removes the row from the list."""
    import uuid

    actor = await seed_user(app_session, email="owner-billed@example.com")
    customer = await seed_customer(app_session)

    bill_item = await seed_billable_bill_item(
        app_session, actor_user_id=actor.id, customer_id=customer.id
    )
    # Pretend it was already billed by stamping an arbitrary uuid.
    bill_item.billed_invoice_item_id = uuid.uuid4()
    await app_session.commit()

    rows = await billable_service.list_unbilled(app_session, customer_id=customer.id)
    assert rows == []


@pytest.mark.asyncio
async def test_list_excludes_non_billable_rows(app_session: AsyncSession) -> None:
    actor = await seed_user(app_session, email="owner-nb@example.com")
    customer = await seed_customer(app_session)
    await seed_billable_bill_item(
        app_session,
        actor_user_id=actor.id,
        customer_id=customer.id,
        is_billable=False,
    )
    rows = await billable_service.list_unbilled(app_session, customer_id=customer.id)
    assert rows == []


@pytest.mark.asyncio
async def test_list_excludes_wrong_customer(app_session: AsyncSession) -> None:
    actor = await seed_user(app_session, email="owner-wc@example.com")
    customer_a = await seed_customer(app_session, display_name="Cust A")
    customer_b = await seed_customer(app_session, display_name="Cust B")
    await seed_billable_bill_item(app_session, actor_user_id=actor.id, customer_id=customer_a.id)
    rows = await billable_service.list_unbilled(app_session, customer_id=customer_b.id)
    assert rows == []
