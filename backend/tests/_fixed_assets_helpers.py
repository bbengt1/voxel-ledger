"""Shared helpers for fixed-assets tests (Phase 9.1, #153)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.account import Account
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
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


async def _ensure_open_period(session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    existing = (await session.execute(select(AccountingPeriod).limit(1))).scalar_one_or_none()
    if existing is None:
        session.add(
            AccountingPeriod(
                id=uuid.uuid4(),
                name="phase91-test-period",
                start_date=today - timedelta(days=60),
                end_date=today + timedelta(days=60),
                state=AccountingPeriodState.OPEN.value,
            )
        )
        await session.flush()


async def seed_acquisition_stack(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed accounts + an open accounting period sufficient for a tangible
    asset acquisition via cash.

    Returns dict of UUIDs: ``asset_account_id``, ``accum_dep_account_id``,
    ``dep_exp_account_id``, ``bank_account_id``.
    """
    await _ensure_open_period(session)

    equipment = Account(id=uuid.uuid4(), code="1500", name="Equipment", type="asset")
    accum_dep = Account(id=uuid.uuid4(), code="1599", name="Accumulated Depreciation", type="asset")
    dep_exp = Account(id=uuid.uuid4(), code="6100", name="Depreciation Expense", type="expense")
    bank = Account(id=uuid.uuid4(), code="1000", name="Bank", type="asset")
    session.add_all([equipment, accum_dep, dep_exp, bank])
    await session.flush()
    await session.commit()

    return {
        "asset_account_id": equipment.id,
        "accum_dep_account_id": accum_dep.id,
        "dep_exp_account_id": dep_exp.id,
        "bank_account_id": bank.id,
    }


async def seed_intangible_acquisition_stack(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Same as :func:`seed_acquisition_stack` but with intangible-asset
    naming (Software / Amortization)."""
    await _ensure_open_period(session)

    software = Account(id=uuid.uuid4(), code="1700", name="Software", type="asset")
    accum_dep = Account(id=uuid.uuid4(), code="1799", name="Accumulated Amortization", type="asset")
    dep_exp = Account(id=uuid.uuid4(), code="6200", name="Amortization Expense", type="expense")
    bank = Account(id=uuid.uuid4(), code="1001", name="Bank Intangible", type="asset")
    session.add_all([software, accum_dep, dep_exp, bank])
    await session.flush()
    await session.commit()

    return {
        "asset_account_id": software.id,
        "accum_dep_account_id": accum_dep.id,
        "dep_exp_account_id": dep_exp.id,
        "bank_account_id": bank.id,
    }


def sample_acquire_body(
    *,
    accounts: dict[str, uuid.UUID],
    kind: str = "tangible",
    asset_class: str = "computer",
    cost: str = "1200.00",
    name: str = "MacBook Pro",
    **extra,
) -> dict:
    body: dict = {
        "name": name,
        "kind": kind,
        "asset_class": asset_class,
        "acquired_on": datetime.now(UTC).date().isoformat(),
        "acquisition_cost": cost,
        "salvage_value": "0",
        "useful_life_months": 36,
        "depreciation_method": "straight_line",
        "asset_account_id": str(accounts["asset_account_id"]),
        "accumulated_depreciation_account_id": str(accounts["accum_dep_account_id"]),
        "depreciation_expense_account_id": str(accounts["dep_exp_account_id"]),
        "contra_account_id": str(accounts["bank_account_id"]),
    }
    body.update(extra)
    return body
