"""POS scan performance benchmark (Phase 6.4, #96).

Performance budget: 100 sequential scans complete in < 30s with p50 < 300ms.
The scan path is one indexed SELECT on ``product.upc`` + one INSERT-or-UPDATE
on ``pos_cart_item``.
"""

from __future__ import annotations

import time
from statistics import median

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pos_helpers import seed_pos_channel, seed_product_with_barcode
from tests._sales_helpers import auth_header, token_for


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_100_scans_under_30s(client: AsyncClient, app_session: AsyncSession) -> None:
    """100 scans against a populated catalog complete in < 30s, p50 < 300ms."""
    channel = await seed_pos_channel(app_session)

    # Seed 100 products with distinct barcodes — populates the catalog so
    # the indexed lookup is the realistic hot path.
    barcodes = [f"PERF-{i:04d}" for i in range(100)]
    for bc in barcodes:
        await seed_product_with_barcode(app_session, barcode=bc, unit_price="1.00")

    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/pos/carts",
        headers=auth_header(owner),
        json={"channel_id": str(channel.id)},
    )
    cart_id = r.json()["id"]

    durations_ms: list[float] = []
    start_all = time.perf_counter()
    for bc in barcodes:
        t0 = time.perf_counter()
        r = await client.post(
            f"/api/v1/pos/carts/{cart_id}/scan",
            headers=auth_header(owner),
            json={"barcode": bc},
        )
        durations_ms.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200, r.text
    elapsed = time.perf_counter() - start_all

    p50 = median(durations_ms)
    print(f"\n100 scans: total={elapsed:.2f}s, p50={p50:.1f}ms, max={max(durations_ms):.1f}ms")
    assert elapsed < 30.0, f"100 scans took {elapsed:.2f}s, budget is 30s"
    assert p50 < 300.0, f"p50 latency {p50:.1f}ms exceeds 300ms budget"
