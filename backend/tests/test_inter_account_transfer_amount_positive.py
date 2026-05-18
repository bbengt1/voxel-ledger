"""Transfer rejects non-positive amount (Phase 8.11, #138)."""

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
@pytest.mark.parametrize("amount", ["0", "-1.00", "-100.50"])
async def test_transfer_rejects_nonpositive_amount(
    amount: str, client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    await seed_open_period(app_session)
    src = await seed_bank_account(app_session, code="1010", name="Checking")
    dst = await seed_bank_account(app_session, code="1011", name="Savings")

    r = await client.post(
        "/api/v1/inter-account-transfers",
        json={
            "from_account_id": str(src.id),
            "to_account_id": str(dst.id),
            "amount": amount,
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        headers=auth_header(token),
    )
    assert r.status_code == 400
    assert "amount" in r.text.lower()
