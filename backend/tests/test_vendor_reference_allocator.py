"""Vendor number allocator (Phase 8.1, #128).

Sequential vendor creation must issue distinct ``VEND-YYYY-NNNN`` values
via the race-safe upsert allocator pattern.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._vendors_helpers import auth_header, token_for


@pytest.mark.asyncio
async def test_sequential_allocation_distinct(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)

    numbers: set[str] = set()
    for i in range(5):
        r = await client.post(
            "/api/v1/vendors",
            headers=auth_header(owner),
            json={"display_name": f"Vendor {i}"},
        )
        assert r.status_code == 201, r.text
        numbers.add(r.json()["vendor_number"])

    assert len(numbers) == 5
    for n in numbers:
        assert n.startswith("VEND-")


@pytest.mark.asyncio
async def test_allocator_advances_monotonically(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Each allocation strictly advances the suffix (no reuse).

    True concurrent allocation under SQLite is single-threaded by the
    aiosqlite event loop, so we exercise the upsert allocator
    sequentially here; the dedicated race property test for the
    allocator lives in ``test_reference_number_allocate_pg.py`` and
    exercises real Postgres via testcontainers.
    """
    owner = await token_for(Role.OWNER, client, app_session)
    suffixes: list[int] = []
    for i in range(4):
        r = await client.post(
            "/api/v1/vendors",
            headers=auth_header(owner),
            json={"display_name": f"Vendor {i}"},
        )
        assert r.status_code == 201, r.text
        num = r.json()["vendor_number"]
        suffix = int(num.rsplit("-", 1)[1])
        suffixes.append(suffix)
    assert suffixes == sorted(suffixes)
    assert len(set(suffixes)) == 4
