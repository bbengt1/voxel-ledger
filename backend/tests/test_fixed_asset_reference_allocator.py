"""ASSET-YYYY-NNNN allocator yields unique sequential references (Phase 9.1, #153)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._fixed_assets_helpers import (
    auth_header,
    sample_acquire_body,
    seed_acquisition_stack,
    token_for,
)


@pytest.mark.asyncio
async def test_sequential_allocation_distinct(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    accounts = await seed_acquisition_stack(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    numbers: set[str] = set()
    suffixes: list[int] = []
    for _ in range(5):
        r = await client.post(
            "/api/v1/fixed-assets",
            headers=auth_header(owner),
            json=sample_acquire_body(accounts=accounts),
        )
        assert r.status_code == 201, r.text
        num = r.json()["asset_number"]
        numbers.add(num)
        assert num.startswith("ASSET-")
        suffixes.append(int(num.rsplit("-", 1)[1]))

    assert len(numbers) == 5
    assert suffixes == sorted(suffixes)
