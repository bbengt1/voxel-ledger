"""Role matrix for bill-payments endpoints (Phase 8.3, #130).

* write (record / unapply / bounce / cancel): owner + bookkeeper
* read: + sales + viewer
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._bill_payments_helpers import (
    auth_header,
    seed_full_ap_payments_stack,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_viewer_can_read_but_not_write(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await seed_full_ap_payments_stack(app_session)
    viewer = await token_for(Role.VIEWER, client, app_session)
    vendor = await seed_vendor(app_session)

    r = await client.get("/api/v1/bill-payments", headers=auth_header(viewer))
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(viewer),
        json={"vendor_id": str(vendor.id), "method": "cash", "amount": "10.00"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_sales_blocked_from_writes(client: AsyncClient, app_session: AsyncSession) -> None:
    """Sales can read but not write — write is owner + bookkeeper only."""
    await seed_full_ap_payments_stack(app_session)
    sales = await token_for(Role.SALES, client, app_session)
    vendor = await seed_vendor(app_session)

    r = await client.get("/api/v1/bill-payments", headers=auth_header(sales))
    assert r.status_code == 200

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(sales),
        json={"vendor_id": str(vendor.id), "method": "cash", "amount": "10.00"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bookkeeper_can_write(client: AsyncClient, app_session: AsyncSession) -> None:
    await seed_full_ap_payments_stack(app_session)
    bookkeeper = await token_for(Role.BOOKKEEPER, client, app_session)
    vendor = await seed_vendor(app_session)

    r = await client.post(
        "/api/v1/bill-payments",
        headers=auth_header(bookkeeper),
        json={"vendor_id": str(vendor.id), "method": "cash", "amount": "10.00"},
    )
    assert r.status_code == 201
