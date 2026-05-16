"""Invoice number allocator races (Phase 7.3, #111).

Concurrent invoice creation must issue distinct ``INV-YYYY-NNNN`` values
(the race-safe upsert allocator pattern that fixed v1 issue #243).
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import (
    auth_header,
    sample_invoice_body,
    seed_customer,
    token_for,
)


@pytest.mark.asyncio
async def test_sequential_allocation_distinct(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    numbers: set[str] = set()
    for _ in range(5):
        r = await client.post(
            "/api/v1/invoices",
            headers=auth_header(owner),
            json=sample_invoice_body(customer_id=str(customer.id)),
        )
        assert r.status_code == 201
        numbers.add(r.json()["invoice_number"])

    assert len(numbers) == 5
    for n in numbers:
        assert n.startswith("INV-")


@pytest.mark.asyncio
async def test_allocator_advances_monotonically(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Each allocation strictly advances the suffix (no reuse).

    True concurrent allocation under SQLite is single-threaded by the
    aiosqlite event loop, so we exercise the upsert allocator
    sequentially here; the dedicated race property test for the
    allocator lives in ``test_reference_number.py`` and exercises real
    Postgres via testcontainers.
    """
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    suffixes: list[int] = []
    for _ in range(4):
        r = await client.post(
            "/api/v1/invoices",
            headers=auth_header(owner),
            json=sample_invoice_body(customer_id=str(customer.id)),
        )
        assert r.status_code == 201, r.text
        num = r.json()["invoice_number"]
        suffix = int(num.rsplit("-", 1)[1])
        suffixes.append(suffix)
    assert suffixes == sorted(suffixes)
    assert len(set(suffixes)) == 4
