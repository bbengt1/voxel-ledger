"""Cancel a settlement from state=imported (Phase 9.8, #160)."""

from __future__ import annotations

from datetime import date

import pytest
from app.models.auth import Role
from app.models.settlement import SettlementState
from app.services import settlement_imports as service
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import (
    auth_header,
    sample_etsy_csv_bytes,
    seed_settlement_stack,
    seed_user,
    token_for,
)


@pytest.mark.asyncio
async def test_cancel_from_imported(client, app_session: AsyncSession) -> None:
    _ = client
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session)

    settlement = await service.import_file(
        session=app_session,
        channel_id=stack["channel_id"],
        file_bytes=sample_etsy_csv_bytes(),
        filename="etsy.csv",
        format_kind="etsy",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert settlement.state == SettlementState.IMPORTED

    cancelled = await service.cancel(
        session=app_session, settlement_id=settlement.id, actor_user_id=user.id
    )
    await app_session.commit()
    assert cancelled.state == SettlementState.CANCELLED


@pytest.mark.asyncio
async def test_cancel_endpoint(client: AsyncClient, app_session: AsyncSession) -> None:
    stack = await seed_settlement_stack(app_session)
    token = await token_for(Role.OWNER, client, app_session)

    csv_bytes = sample_etsy_csv_bytes()
    r = await client.post(
        "/api/v1/settlements",
        headers=auth_header(token),
        data={
            "channel_id": str(stack["channel_id"]),
            "format_kind": "etsy",
            "period_start": "2026-03-01",
            "period_end": "2026-03-31",
            "payout_account_id": str(stack["payout_account_id"]),
        },
        files={"file": ("etsy.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 201, r.text
    settlement_id = r.json()["id"]

    r2 = await client.post(
        f"/api/v1/settlements/{settlement_id}/cancel", headers=auth_header(token)
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["state"] == "cancelled"
