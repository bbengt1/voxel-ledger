"""POS: unknown barcode returns 404 with a helpful body (Phase 6.4, #96)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pos_helpers import seed_pos_channel
from tests._sales_helpers import auth_header, token_for


@pytest.mark.asyncio
async def test_unknown_barcode_404(client: AsyncClient, app_session: AsyncSession) -> None:
    channel = await seed_pos_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    r = await client.post(
        "/api/v1/pos/carts",
        headers=auth_header(owner),
        json={"channel_id": str(channel.id)},
    )
    cart_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/pos/carts/{cart_id}/scan",
        headers=auth_header(owner),
        json={"barcode": "NOPE-NOT-A-THING"},
    )
    assert r.status_code == 404
    body = r.json()
    assert "NOPE-NOT-A-THING" in body["detail"]
