"""Shared helpers for payments / credit-notes / debit-notes tests (Phase 7.4, #112)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.auth import Role
from app.services import customers as customers_service
from app.services import invoices as invoices_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_owner(session: AsyncSession, *, email: str = "owner@example.com"):
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    return user


async def seed_full_ar_stack(
    session: AsyncSession,
):
    """Set up: open period + AR/Rev/Tax/Bank accounts + all settings."""
    from app.models.account import Account
    from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
    from app.services.settings.service import SettingsService
    from sqlalchemy import select

    today = datetime.now(UTC).date()
    existing = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one_or_none()
    if existing is None:
        session.add(
            AccountingPeriod(
                id=uuid.uuid4(),
                name="phase74-test-period",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=30),
                state=AccountingPeriodState.OPEN.value,
            )
        )

    ar_account = Account(id=uuid.uuid4(), code="1200", name="AR", type="asset")
    revenue_account = Account(id=uuid.uuid4(), code="4000", name="Revenue", type="revenue")
    bank_account = Account(id=uuid.uuid4(), code="1010", name="Bank", type="asset")
    session.add_all([ar_account, revenue_account, bank_account])
    await session.flush()

    await SettingsService.set(
        "ar.default_ar_account_id", ar_account.id, session=session, actor_user_id=None
    )
    await SettingsService.set(
        "ar.default_revenue_account_id",
        revenue_account.id,
        session=session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "ar.default_bank_account_id",
        bank_account.id,
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    return {
        "ar_account_id": ar_account.id,
        "revenue_account_id": revenue_account.id,
        "bank_account_id": bank_account.id,
    }


async def seed_customer(session: AsyncSession, *, display_name: str = "Acme Corp"):
    customer = await customers_service.create(
        session,
        display_name=display_name,
        payment_terms_days=30,
        actor_user_id=None,
    )
    await session.commit()
    return customer


async def seed_issued_invoice(
    session: AsyncSession,
    *,
    customer,
    actor_user_id: uuid.UUID,
    unit_price: str = "100.00",
    quantity: str = "1",
):
    invoice = await invoices_service.create_draft(
        session,
        customer_id=customer.id,
        items=[
            {
                "kind": "manual",
                "description": "Widget",
                "quantity": quantity,
                "unit_price": unit_price,
            }
        ],
        actor_user_id=actor_user_id,
    )
    await session.commit()
    invoice = await invoices_service.issue(
        session, invoice_id=invoice.id, actor_user_id=actor_user_id
    )
    await session.commit()
    return invoice
