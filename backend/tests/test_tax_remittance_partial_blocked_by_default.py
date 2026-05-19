"""Partial-payment guard: amount < outstanding requires allow_partial=true (Phase 9.6, #158)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._tax_remittance_helpers import (
    auth_header,
    post_tax_collection,
    seed_tax_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_partial_blocked_by_default(client: AsyncClient, app_session: AsyncSession) -> None:
    accounts = await seed_tax_stack(app_session)
    owner, user = await token_for(Role.OWNER, client, app_session)

    await post_tax_collection(
        app_session,
        accounts=accounts,
        subtotal="100.00",
        tax="10.00",
        actor_user_id=user.id,
    )

    today = datetime.now(UTC).date()
    body = {
        "profile_id": str(accounts["profile_id"]),
        "period_start": today.replace(day=1).isoformat(),
        "period_end": today.isoformat(),
        "amount_paid": "5.00",  # partial!
        "paid_on": today.isoformat(),
        "method": "check",
        "bank_account_id": str(accounts["bank_account_id"]),
    }
    r = await client.post("/api/v1/tax-remittances", headers=auth_header(owner), json=body)
    assert r.status_code == 409, r.text
    assert "allow_partial" in r.text.lower()


@pytest.mark.asyncio
async def test_partial_allowed_when_flag_set(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_tax_stack(app_session)
    owner, user = await token_for(Role.OWNER, client, app_session)

    await post_tax_collection(
        app_session,
        accounts=accounts,
        subtotal="100.00",
        tax="10.00",
        actor_user_id=user.id,
    )

    today = datetime.now(UTC).date()
    body = {
        "profile_id": str(accounts["profile_id"]),
        "period_start": today.replace(day=1).isoformat(),
        "period_end": today.isoformat(),
        "amount_paid": "5.00",
        "paid_on": today.isoformat(),
        "method": "check",
        "bank_account_id": str(accounts["bank_account_id"]),
        "allow_partial": True,
    }
    r = await client.post("/api/v1/tax-remittances", headers=auth_header(owner), json=body)
    assert r.status_code == 201, r.text
    assert r.json()["amount_paid"] == "5.000000"
