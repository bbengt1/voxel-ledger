"""Bill number allocator (Phase 8.2, #129)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bills_helpers import (
    auth_header,
    sample_bill_body,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_sequential_allocation_distinct(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    numbers: set[str] = set()
    for _ in range(5):
        r = await client.post(
            "/api/v1/bills",
            headers=auth_header(owner),
            json=sample_bill_body(vendor_id=str(vendor.id)),
        )
        assert r.status_code == 201
        numbers.add(r.json()["bill_number"])

    assert len(numbers) == 5
    for n in numbers:
        assert n.startswith("BILL-")


@pytest.mark.asyncio
async def test_allocator_advances_monotonically(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    vendor = await seed_vendor(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    suffixes: list[int] = []
    for _ in range(4):
        r = await client.post(
            "/api/v1/bills",
            headers=auth_header(owner),
            json=sample_bill_body(vendor_id=str(vendor.id)),
        )
        assert r.status_code == 201, r.text
        num = r.json()["bill_number"]
        suffix = int(num.rsplit("-", 1)[1])
        suffixes.append(suffix)
    assert suffixes == sorted(suffixes)
    assert len(set(suffixes)) == 4
