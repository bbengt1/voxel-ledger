"""Shared helpers for recurring invoices tests (Phase 7.5, #113)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.auth import Role
from app.services import customers as customers_service
from app.services import recurring_invoices as service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"recurring-{role.value}@example.com"
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


async def seed_user(session: AsyncSession, *, email: str = "owner-recurring@example.com"):
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


async def seed_customer(session: AsyncSession, *, display_name: str = "Subscription Co"):
    customer = await customers_service.create(
        session,
        display_name=display_name,
        billing_address={"line1": "123 Way", "city": "City", "country": "US"},
        payment_terms_days=30,
        actor_user_id=None,
    )
    await session.commit()
    return customer


def sample_template_body(*, customer_id: str, **extra) -> dict:
    body: dict = {
        "customer_id": customer_id,
        "name": "Monthly retainer",
        "cadence_kind": "monthly",
        "cadence_interval": 1,
        "start_at": datetime.now(UTC).isoformat(),
        "auto_issue": False,
        "items": [
            {
                "kind": "manual",
                "description": "Retainer line",
                "quantity": "1",
                "unit_price": "100.00",
            }
        ],
    }
    body.update(extra)
    return body


async def create_template(
    session: AsyncSession,
    *,
    customer_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    start_at: datetime | None = None,
    cadence_kind: str = "monthly",
    cadence_interval: int = 1,
    auto_issue: bool = False,
    name: str = "Monthly retainer",
    end_at: datetime | None = None,
    unit_price: str = "100.00",
):
    start_at = start_at or datetime.now(UTC) - timedelta(minutes=5)
    template = await service.create(
        session,
        customer_id=customer_id,
        name=name,
        cadence_kind=cadence_kind,
        cadence_interval=cadence_interval,
        start_at=start_at,
        end_at=end_at,
        auto_issue=auto_issue,
        items=[
            {
                "kind": "manual",
                "description": "Retainer line",
                "quantity": "1",
                "unit_price": unit_price,
            }
        ],
        actor_user_id=actor_user_id,
    )
    await session.commit()
    return template
