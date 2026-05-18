"""Shared helpers for expense-claims tests (Phase 8.7, #134)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.auth import Role
from app.services import expense_categories as expense_categories_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-claims@example.com"
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


async def seed_user(
    session: AsyncSession,
    *,
    email: str = "owner-claims@example.com",
    role: Role = Role.OWNER,
):
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    return user


async def seed_full_expense_claim_stack(
    session: AsyncSession,
    *,
    threshold: Decimal | None = None,
):
    """Seed accounts + settings + open accounting period + an expense
    category for the claim flow.

    Returns dict with keys: expense_account_id, reimbursable_account_id,
    expense_category_id.
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
                name="phase87-test-period",
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=30),
                state=AccountingPeriodState.OPEN.value,
            )
        )

    expense_account = Account(id=uuid.uuid4(), code="5100", name="Travel Expenses", type="expense")
    reimbursable_account = Account(
        id=uuid.uuid4(),
        code="2100",
        name="Employee Reimbursable",
        type="liability",
    )
    session.add_all([expense_account, reimbursable_account])
    await session.flush()

    await SettingsService.set(
        "ap.employee_reimbursable_account_id",
        reimbursable_account.id,
        session=session,
        actor_user_id=None,
    )
    if threshold is not None:
        await SettingsService.set(
            "ap.expense_claim_approval_threshold",
            threshold,
            session=session,
            actor_user_id=None,
        )
    await session.commit()

    category = await expense_categories_service.create(
        session,
        code=f"TRV-{uuid.uuid4().hex[:6]}",
        name="Travel",
        default_expense_account_id=expense_account.id,
        actor_user_id=None,
    )
    await session.commit()

    return {
        "expense_account_id": expense_account.id,
        "reimbursable_account_id": reimbursable_account.id,
        "expense_category_id": category.id,
    }


def sample_claim_lines(*, expense_category_id, amount: str = "50.00") -> list[dict]:
    return [
        {
            "expense_category_id": str(expense_category_id),
            "description": "Taxi to airport",
            "amount": amount,
            "occurred_on": datetime.now(UTC).date().isoformat(),
            "is_billable": False,
            "markup_percent": "0",
        }
    ]
