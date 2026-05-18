"""Finalized reconciliations are locked (Phase 8.11, #138)."""

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
async def test_finalize_locks_clearing_and_refinalize(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)
    today = datetime.now(UTC).date()
    period_start = today - timedelta(days=10)
    await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="A",
        amount=Decimal("100.00"),
        occurred_on=period_start + timedelta(days=1),
    )

    r = await client.post(
        "/api/v1/bank-reconciliations",
        json={
            "account_id": str(bank.id),
            "period_start": period_start.isoformat(),
            "period_end": today.isoformat(),
            "statement_ending_balance": "100.00",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201
    recon = r.json()
    item_id = recon["items"][0]["id"]

    await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/items/{item_id}/clear",
        headers=auth_header(token),
    )
    r = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/finalize",
        headers=auth_header(token),
    )
    assert r.status_code == 200

    # Refinalize -> 400.
    r2 = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/finalize",
        headers=auth_header(token),
    )
    assert r2.status_code == 400

    # Unclear (or clear) the item after finalize -> rejected.
    r3 = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/items/{item_id}/unclear",
        headers=auth_header(token),
    )
    assert r3.status_code == 400
