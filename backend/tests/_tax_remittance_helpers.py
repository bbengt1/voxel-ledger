"""Shared helpers for tax-remittance + tax-liability-report tests (Phase 9.6, #158)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.account import Account
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.models.auth import Role
from app.services import journal_entries as journal_service
from app.services import tax as tax_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession):
    """Create a user with the given role and log in. Returns (token, user)."""
    email = f"{role.value}@example.com"
    user = await create_user(
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
    return r.json()["access_token"], user


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


async def _ensure_open_period(session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    existing = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one_or_none()
    if existing is None:
        session.add(
            AccountingPeriod(
                id=uuid.uuid4(),
                name="phase96-test-period",
                start_date=today - timedelta(days=180),
                end_date=today + timedelta(days=60),
                state=AccountingPeriodState.OPEN.value,
            )
        )
        await session.flush()
        await session.commit()


async def seed_tax_stack(
    session: AsyncSession,
    *,
    rate_value: Decimal | str = "0.10",
):
    """Seed accounts, period, and a single-rate tax profile.

    Returns a dict with: ``profile_id``, ``rate_id``, ``liability_account_id``,
    ``bank_account_id``, ``sales_account_id``.
    """
    await _ensure_open_period(session)

    bank = Account(id=uuid.uuid4(), code="1000", name="Bank", type="asset")
    liability = Account(id=uuid.uuid4(), code="2210", name="Tax Liability", type="liability")
    sales = Account(id=uuid.uuid4(), code="4000", name="Sales Revenue", type="revenue")
    session.add_all([bank, liability, sales])
    await session.flush()
    await session.commit()

    profile = await tax_service.create_profile(
        session,
        code="US-CA-TEST",
        name="California Test",
        jurisdiction="US-CA",
        is_reverse_charge=False,
        notes=None,
        actor_user_id=None,
    )
    rate = await tax_service.add_rate(
        session,
        profile_id=profile.id,
        ordinal=0,
        name="State Sales Tax",
        rate=Decimal(str(rate_value)),
        liability_account_id=liability.id,
        compound_on_previous=False,
        actor_user_id=None,
    )
    await session.commit()
    return {
        "profile_id": profile.id,
        "rate_id": rate.id,
        "liability_account_id": liability.id,
        "bank_account_id": bank.id,
        "sales_account_id": sales.id,
    }


async def post_tax_collection(
    session: AsyncSession,
    *,
    accounts: dict,
    subtotal: Decimal | str,
    tax: Decimal | str,
    actor_user_id: uuid.UUID,
    when: datetime | None = None,
) -> None:
    """Post a balanced JE simulating a taxable sale.

    Dr Bank (subtotal + tax) / Cr Sales (subtotal) / Cr Tax Liability (tax).
    """
    subtotal_d = Decimal(str(subtotal))
    tax_d = Decimal(str(tax))
    total = subtotal_d + tax_d
    posted_at = when or datetime.now(UTC)
    await journal_service.post(
        journal_service.JournalEntryInput(
            description="Test taxable sale",
            posted_at=posted_at,
            lines=[
                journal_service.JournalLineInput(
                    account_id=accounts["bank_account_id"],
                    debit=total,
                    credit=Decimal("0"),
                    line_number=1,
                ),
                journal_service.JournalLineInput(
                    account_id=accounts["sales_account_id"],
                    debit=Decimal("0"),
                    credit=subtotal_d,
                    line_number=2,
                ),
                journal_service.JournalLineInput(
                    account_id=accounts["liability_account_id"],
                    debit=Decimal("0"),
                    credit=tax_d,
                    line_number=3,
                ),
            ],
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    await session.commit()
