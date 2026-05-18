"""Finalize is gated by the rounding-tolerance check (Phase 8.11, #138)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    seed_bank_account,
    seed_bank_transaction,
    token_for,
)


async def _open_recon(
    client: AsyncClient,
    token: str,
    *,
    account_id: str,
    period_start,
    period_end,
    statement_balance: str,
) -> dict:
    r = await client.post(
        "/api/v1/bank-reconciliations",
        json={
            "account_id": account_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "statement_ending_balance": statement_balance,
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_finalize_rejected_when_difference_nonzero(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)
    today = datetime.now(UTC).date()
    period_start = today - timedelta(days=10)

    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="A",
        amount=Decimal("100.00"),
        occurred_on=period_start + timedelta(days=1),
    )

    # Statement says 50; book will be 100 when item cleared -> diff -50.
    recon = await _open_recon(
        client,
        token,
        account_id=str(bank.id),
        period_start=period_start,
        period_end=today,
        statement_balance="50.00",
    )
    # Item starts unmatched/uncleared. Clear it -> book becomes 100.
    item_id = recon["items"][0]["id"]
    assert recon["items"][0]["bank_transaction_id"] == str(tx.id)
    r = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/items/{item_id}/clear",
        headers=auth_header(token),
    )
    assert r.status_code == 200

    r = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/finalize",
        headers=auth_header(token),
    )
    assert r.status_code == 400
    assert "difference" in r.text.lower() or "tolerance" in r.text.lower()


@pytest.mark.asyncio
async def test_finalize_succeeds_when_exact(client: AsyncClient, app_session: AsyncSession) -> None:
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
    recon = await _open_recon(
        client,
        token,
        account_id=str(bank.id),
        period_start=period_start,
        period_end=today,
        statement_balance="100.00",
    )
    item_id = recon["items"][0]["id"]
    await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/items/{item_id}/clear",
        headers=auth_header(token),
    )
    r = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/finalize",
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "finalized"


@pytest.mark.asyncio
async def test_finalize_succeeds_within_tolerance(
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

    # Configure a 1-cent tolerance.
    await SettingsService.set(
        "banking.reconciliation_rounding_tolerance",
        Decimal("0.01"),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    recon = await _open_recon(
        client,
        token,
        account_id=str(bank.id),
        period_start=period_start,
        period_end=today,
        statement_balance="100.01",
    )
    item_id = recon["items"][0]["id"]
    await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/items/{item_id}/clear",
        headers=auth_header(token),
    )
    r = await client.post(
        f"/api/v1/bank-reconciliations/{recon['id']}/finalize",
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "finalized"
