"""CSV export of the tax-liability report (Phase 9.6, #158)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
async def test_csv_format(client: AsyncClient, app_session: AsyncSession) -> None:
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
    date_from = (today - timedelta(days=30)).isoformat()
    date_to = today.isoformat()
    resp = await client.get(
        f"/api/v1/reports/tax-liability?date_from={date_from}&date_to={date_to}&format=csv",
        headers=auth_header(owner),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.text
    lines = body.strip().splitlines()
    # Header + one row + grand total
    assert len(lines) == 3
    header = lines[0].split(",")
    assert header[0] == "profile_code"
    assert "tax_collected" in header
    assert "tax_remitted" in header
    assert "net_liability" in header
    # Last line is the grand total
    assert lines[-1].startswith("GRAND TOTAL,")
