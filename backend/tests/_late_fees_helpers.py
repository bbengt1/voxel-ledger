"""Shared helpers for Phase 7.6 (#114) late-fee + AR aging tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.invoice import Invoice, InvoiceState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._payments_helpers import (
    seed_customer,  # noqa: F401  (re-exported for callers)
    seed_full_ar_stack,  # noqa: F401
    seed_issued_invoice,
    seed_owner,  # noqa: F401
)


async def seed_overdue_invoice(
    session: AsyncSession,
    *,
    customer,
    actor_user_id: uuid.UUID,
    unit_price: str = "100.00",
    days_past_due: int = 5,
) -> Invoice:
    """Issue an invoice, then back-date ``due_at`` to make it overdue."""
    invoice = await seed_issued_invoice(
        session, customer=customer, actor_user_id=actor_user_id, unit_price=unit_price
    )
    invoice = (await session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one()
    invoice.due_at = datetime.now(UTC) - timedelta(days=days_past_due)
    await session.commit()
    return invoice


async def force_state(
    session: AsyncSession,
    *,
    invoice_id: uuid.UUID,
    state: InvoiceState,
) -> None:
    inv = (await session.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one()
    inv.state = state
    await session.commit()


async def get_invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    return (await session.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one()
