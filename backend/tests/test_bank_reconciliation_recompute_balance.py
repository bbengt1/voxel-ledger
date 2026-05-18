"""Explicit recompute updates book balance + difference (Phase 8.11, #138)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    seed_bank_account,
    seed_bank_transaction,
    token_for,
)


@pytest.mark.asyncio
async def test_recompute_updates_balance_and_difference(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)
    today = datetime.now(UTC).date()
    period_start = today - timedelta(days=10)

    await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="DEPOSIT",
        amount=Decimal("250.00"),
        occurred_on=period_start + timedelta(days=1),
    )
    await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="WITHDRAW",
        amount=Decimal("-50.00"),
        occurred_on=period_start + timedelta(days=2),
    )

    r = await client.post(
        "/api/v1/bank-reconciliations",
        json={
            "account_id": str(bank.id),
            "period_start": period_start.isoformat(),
            "period_end": today.isoformat(),
            "statement_ending_balance": "200.00",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201
    recon = r.json()
    # Nothing cleared initially → book = 0, diff = 200.
    assert Decimal(recon["book_ending_balance"]) == Decimal("0")
    assert Decimal(recon["difference"]) == Decimal("200.00")

    # Clear both items.
    for item in recon["items"]:
        await client.post(
            f"/api/v1/bank-reconciliations/{recon['id']}/items/{item['id']}/clear",
            headers=auth_header(token),
        )

    # Explicit recompute (idempotent).
    r2 = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/recompute",
        headers=auth_header(token),
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert Decimal(body["book_ending_balance"]) == Decimal("200.00")
    assert Decimal(body["difference"]) == Decimal("0")
    assert body["state"] == "balanced"
