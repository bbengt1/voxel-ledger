"""Shared helpers for expense categories tests (Phase 8.6, #133)."""

from __future__ import annotations

import uuid

from app.models.account import Account
from app.models.auth import Role
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


async def seed_expense_account(
    session: AsyncSession,
    *,
    code: str = "5100",
    name: str = "Office Supplies",
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type="expense")
    session.add(acct)
    await session.commit()
    return acct


async def seed_non_expense_account(
    session: AsyncSession,
    *,
    code: str = "1000",
    name: str = "Cash",
    type_: str = "asset",
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type=type_)
    session.add(acct)
    await session.commit()
    return acct
