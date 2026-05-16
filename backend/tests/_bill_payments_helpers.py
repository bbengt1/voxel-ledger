"""Shared helpers for bill payments tests (Phase 8.3, #130)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.auth import Role
from app.services import bills as bills_service
from app.services import vendors as vendors_service
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


async def seed_full_ap_payments_stack(session: AsyncSession):
    """Open period + Expense/AP/Bank accounts + all AP settings.

    Returns dict of account IDs.
    """
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
                name="phase83-test-period",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=30),
                state=AccountingPeriodState.OPEN.value,
            )
        )

    expense_account = Account(id=uuid.uuid4(), code="5000", name="Expenses", type="expense")
    ap_account = Account(id=uuid.uuid4(), code="2000", name="AP", type="liability")
    bank_account = Account(id=uuid.uuid4(), code="1010", name="Bank", type="asset")
    session.add_all([expense_account, ap_account, bank_account])
    await session.flush()

    await SettingsService.set(
        "ap.default_expense_account_id",
        expense_account.id,
        session=session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "ap.default_ap_account_id",
        ap_account.id,
        session=session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "ap.default_bank_account_id",
        bank_account.id,
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    return {
        "expense_account_id": expense_account.id,
        "ap_account_id": ap_account.id,
        "bank_account_id": bank_account.id,
    }


async def seed_vendor(
    session: AsyncSession,
    *,
    display_name: str = "Acme Supplies",
):
    vendor = await vendors_service.create(
        session,
        display_name=display_name,
        payment_terms_days=30,
        actor_user_id=None,
    )
    await session.commit()
    return vendor


async def seed_issued_bill(
    session: AsyncSession,
    *,
    vendor,
    actor_user_id: uuid.UUID,
    unit_price: str = "100.00",
    quantity: str = "1",
):
    bill = await bills_service.create_draft(
        session,
        vendor_id=vendor.id,
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
    bill = await bills_service.issue(session, bill_id=bill.id, actor_user_id=actor_user_id)
    await session.commit()
    return bill
