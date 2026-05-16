"""Shared helpers for quotes tests (Phase 7.2, #110)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.auth import Role
from app.services import customers as customers_service
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


async def seed_customer(
    session: AsyncSession,
    *,
    display_name: str = "Acme Corp",
    billing_address: dict | None = None,
):
    customer = await customers_service.create(
        session,
        display_name=display_name,
        billing_address=billing_address,
        actor_user_id=None,
    )
    await session.commit()
    return customer


def sample_quote_body(*, customer_id: str, items: list[dict] | None = None, **extra) -> dict:
    body: dict = {
        "customer_id": customer_id,
        "discount_amount": "0",
        "tax_amount": "0",
        "items": items
        if items is not None
        else [
            {
                "kind": "manual",
                "description": "Custom widget",
                "quantity": "2",
                "unit_price": "10.00",
            }
        ],
    }
    body.update(extra)
    return body


def isoformat_now() -> str:
    return datetime.now(UTC).isoformat()


def random_uuid() -> str:
    return str(uuid.uuid4())
