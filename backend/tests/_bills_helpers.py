"""Shared helpers for bills tests (Phase 8.2, #129)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.auth import Role
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


async def seed_user(session: AsyncSession, *, email: str = "owner@example.com"):
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


async def seed_vendor(
    session: AsyncSession,
    *,
    display_name: str = "Acme Supplies",
    billing_address: dict | None = None,
    payment_terms_days: int = 30,
):
    vendor = await vendors_service.create(
        session,
        display_name=display_name,
        billing_address=billing_address,
        payment_terms_days=payment_terms_days,
        actor_user_id=None,
    )
    await session.commit()
    return vendor


def sample_bill_body(*, vendor_id: str, items: list[dict] | None = None, **extra) -> dict:
    body: dict = {
        "vendor_id": vendor_id,
        "discount_amount": "0",
        "tax_amount": "0",
        "items": items
        if items is not None
        else [
            {
                "kind": "manual",
                "description": "Office supplies",
                "quantity": "2",
                "unit_price": "10.00",
            }
        ],
    }
    body.update(extra)
    return body


async def seed_full_ap_stack(session: AsyncSession, *, with_tax: bool = True):
    """Seed accounts + settings + open accounting period for bill issue.

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
                name="phase82-test-period",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=30),
                state=AccountingPeriodState.OPEN.value,
            )
        )

    expense_account = Account(id=uuid.uuid4(), code="5000", name="Expenses", type="expense")
    ap_account = Account(id=uuid.uuid4(), code="2000", name="AP", type="liability")
    tax_account = Account(id=uuid.uuid4(), code="5200", name="Tax Expense", type="expense")
    session.add_all([expense_account, ap_account, tax_account])
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
    if with_tax:
        await SettingsService.set(
            "ap.default_tax_expense_account_id",
            tax_account.id,
            session=session,
            actor_user_id=None,
        )
    await session.commit()
    return {
        "expense_account_id": expense_account.id,
        "ap_account_id": ap_account.id,
        "tax_account_id": tax_account.id,
    }


def isoformat_now() -> str:
    return datetime.now(UTC).isoformat()


def random_uuid() -> str:
    return str(uuid.uuid4())
