"""Transfer rejects from_account == to_account (Phase 8.11, #138)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    seed_bank_account,
    seed_open_period,
    token_for,
)


@pytest.mark.asyncio
async def test_transfer_rejects_same_account(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)

    r = await client.post(
        "/api/v1/inter-account-transfers",
        json={
            "from_account_id": str(bank.id),
            "to_account_id": str(bank.id),
            "amount": "10.00",
            "occurred_at": datetime.now(UTC).isoformat(),
            "memo": None,
        },
        headers=auth_header(token),
    )
    assert r.status_code == 400
    assert "differ" in r.text.lower() or "same" in r.text.lower()
