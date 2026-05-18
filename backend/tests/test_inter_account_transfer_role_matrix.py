"""Role gating for inter-account transfers (Phase 8.11, #138)."""

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
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 201),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_role_matrix_for_transfer_post(
    role: Role,
    expected: int,
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    token = await token_for(role, client, app_session)
    await seed_open_period(app_session)
    src = await seed_bank_account(app_session, code="1010", name="A")
    dst = await seed_bank_account(app_session, code="1011", name="B")

    r = await client.post(
        "/api/v1/inter-account-transfers",
        json={
            "from_account_id": str(src.id),
            "to_account_id": str(dst.id),
            "amount": "10.00",
            "occurred_at": datetime.now(UTC).isoformat(),
        },
        headers=auth_header(token),
    )
    assert r.status_code == expected, r.text
