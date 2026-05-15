"""Shared helpers for jobs/plates tests (Phase 5.2)."""

from __future__ import annotations

from decimal import Decimal

from app.models.auth import Role
from app.services import products as products_service
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


async def seed_product(session: AsyncSession, *, name: str = "Widget"):
    product = await products_service.create(
        session,
        name=name,
        description=None,
        unit_price=Decimal("10"),
        actor_user_id=None,
    )
    await session.commit()
    return product
