"""Shared helpers for billable-expenses tests (Phase 8.8, #135).

Seeders create billable ``bill_item`` and ``expense_claim_line`` rows
pointed at a target customer so the unbilled list + invoice-composer
flows have realistic source rows to exercise.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models.bill import BillItem
from app.models.customer import Customer
from app.models.expense_claim import ExpenseClaimLine
from app.services import bills as bills_service
from app.services import customers as customers_service
from app.services import expense_claims as claims_service
from app.services import vendors as vendors_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bills_helpers import seed_full_ap_stack
from tests._expense_claims_helpers import (
    sample_claim_lines,
    seed_full_expense_claim_stack,
)


async def seed_customer(
    session: AsyncSession,
    *,
    display_name: str = "Bill-To Co",
    payment_terms_days: int = 30,
) -> Customer:
    customer = await customers_service.create(
        session,
        display_name=display_name,
        payment_terms_days=payment_terms_days,
        actor_user_id=None,
    )
    await session.commit()
    return customer


async def seed_vendor(
    session: AsyncSession,
    *,
    display_name: str = "Reimbursable Vendor",
    payment_terms_days: int = 30,
):
    vendor = await vendors_service.create(
        session,
        display_name=display_name,
        payment_terms_days=payment_terms_days,
        actor_user_id=None,
    )
    await session.commit()
    return vendor


async def seed_billable_bill_item(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    customer_id: uuid.UUID,
    amount: str = "100.00",
    markup_percent: str = "10",
    description: str = "Subcontractor service",
    is_billable: bool = True,
) -> BillItem:
    """Create a Bill via the bills service then mutate its sole line to
    flag it billable for ``customer_id`` with ``markup_percent``."""
    await seed_full_ap_stack(session, with_tax=False)
    vendor = await seed_vendor(session)
    bill = await bills_service.create_draft(
        session,
        vendor_id=vendor.id,
        items=[
            {
                "kind": "manual",
                "description": description,
                "quantity": "1",
                "unit_price": amount,
            }
        ],
        actor_user_id=actor_user_id,
    )
    await session.commit()
    item = bill.items[0]
    item.is_billable = is_billable
    item.customer_id = customer_id
    item.markup_percent = Decimal(markup_percent)
    await session.commit()
    await session.refresh(item)
    return item


async def seed_billable_expense_claim_line(
    session: AsyncSession,
    *,
    submitter_user_id: uuid.UUID,
    customer_id: uuid.UUID,
    amount: str = "60.00",
    markup_percent: str = "15",
    description: str = "Taxi to client site",
    is_billable: bool = True,
) -> ExpenseClaimLine:
    """Seed expense-claim stack + create a claim with one line, then
    flag the line billable for ``customer_id``."""
    stack = await seed_full_expense_claim_stack(session)
    lines = sample_claim_lines(expense_category_id=stack["expense_category_id"], amount=amount)
    lines[0]["description"] = description
    claim = await claims_service.create_draft(
        session,
        submitter_user_id=submitter_user_id,
        lines=lines,
        actor_user_id=submitter_user_id,
    )
    await session.commit()
    line = claim.lines[0]
    line.is_billable = is_billable
    line.customer_id = customer_id
    line.markup_percent = Decimal(markup_percent)
    await session.commit()
    await session.refresh(line)
    return line


def isoformat_now() -> str:
    return datetime.now(UTC).isoformat()
