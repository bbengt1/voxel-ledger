"""Shared helpers for late-fees / AR-aging tests (Phase 7.6, #114)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from app.models import Base
from app.models.invoice import Invoice, InvoiceState
from app.services import customers as customers_service
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine):
    """Ensure all tables exist on the test engine.

    Phase 7.6 worker/service tests use the plain ``session`` fixture
    (in-memory SQLite); ``Base.metadata.create_all`` is what bridges
    the ORM to the empty schema.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


async def seed_customer_simple(session: AsyncSession, *, display_name: str = "Test Co"):
    customer = await customers_service.create(
        session,
        display_name=display_name,
        billing_address=None,
        payment_terms_days=30,
        actor_user_id=None,
    )
    await session.flush()
    return customer


async def seed_issued_invoice(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    total_amount: Decimal | str = "100.00",
    due_at: datetime,
    state: InvoiceState = InvoiceState.ISSUED,
    issued_at: datetime | None = None,
) -> Invoice:
    """Bypass the issuance pipeline; directly insert a row with the
    state, due_at, and outstanding amount we want for worker testing.

    The Phase 7.3 issuance flow requires a configured chart of accounts
    + open period; for the worker-level tests we just need rows with
    the right shape.
    """
    if issued_at is None:
        issued_at = datetime.now(UTC) - timedelta(days=60)
    total = Decimal(str(total_amount))
    inv_num = f"INV-TEST-{uuid.uuid4().hex[:8]}"
    invoice = Invoice(
        invoice_number=inv_num,
        customer_id=customer_id,
        state=state,
        issued_at=issued_at,
        due_at=due_at,
        subtotal=total,
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=total,
        amount_paid=Decimal("0"),
        amount_outstanding=total,
        currency="USD",
        created_by_user_id=actor_user_id,
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def seed_user_simple(session: AsyncSession):
    from app.models.auth import Role
    from app.services.auth import create_user

    user = await create_user(
        session,
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        password="pw-correct",
        full_name="Test User",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.flush()
    return user
