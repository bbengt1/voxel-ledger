"""Shared helpers for sales tests (Phase 6.2, #94)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.models.auth import Role
from app.services import sales_channels as channels_service
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
    """Seed an owner user; returns the user row. Useful for service-layer
    tests that need a real ``created_by_user_id`` FK target."""
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


async def seed_channel(
    session: AsyncSession,
    *,
    name: str = "Test channel",
    slug: str = "test-channel",
    kind: str = "marketplace",
    fee_model: str = "percent",
    fee_percent: str | None = "0.05",
    fee_flat: str | None = None,
):
    channel = await channels_service.create(
        session,
        name=name,
        slug=slug,
        kind=kind,
        fee_model=fee_model,
        fee_percent=Decimal(fee_percent) if fee_percent else None,
        fee_flat=Decimal(fee_flat) if fee_flat else None,
        actor_user_id=None,
    )
    await session.commit()
    return channel


def sample_sale_body(*, channel_id: str, items: list[dict] | None = None, **extra) -> dict:
    body = {
        "channel_id": channel_id,
        "customer_name": "Test Customer",
        "customer_email": "test@example.com",
        "occurred_at": datetime.now(UTC).isoformat(),
        "discount_amount": "0",
        "shipping_amount": "0",
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
