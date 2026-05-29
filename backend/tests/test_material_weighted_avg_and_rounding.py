"""Material detail response: weighted-average cost + on-hand value +
display rounding (#11 Phase C/D).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _owner_token(client: AsyncClient, session: AsyncSession) -> str:
    from app.models.auth import Role

    from tests.test_materials_endpoints import _token_for

    return await _token_for(Role.OWNER, client, session)


async def _seed_workshop(client: AsyncClient, token: str) -> str:
    r = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(token),
        json={"code": "WS-1", "name": "Workshop", "kind": "workshop"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_weighted_average_across_two_receipts(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """1000 g at $0.02/g + 1000 g at $0.04/g => weighted avg $0.03/g,
    on-hand value $60.00."""
    owner = await _owner_token(client, app_session)
    loc = await _seed_workshop(client, owner)
    await client.put(
        "/api/v1/settings/inventory.default_receiving_location_id",
        headers=_h(owner),
        json={"value": loc},
    )

    mat = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={
            "name": "PLA",
            "material_type": "PLA",
            "spool_weight_grams": 1000,
        },
    )
    assert mat.status_code == 201, mat.text
    mid = mat.json()["id"]

    # First receipt: 1 spool @ $20 → 1000 g, $20, $0.02/g.
    r1 = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=_h(owner),
        json={"spools": 1, "extra_grams": "0", "price_per_spool": "20.00"},
    )
    assert r1.status_code == 201, r1.text
    # Second receipt: 1 spool @ $40 → 1000 g, $40, $0.04/g.
    r2 = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=_h(owner),
        json={"spools": 1, "extra_grams": "0", "price_per_spool": "40.00"},
    )
    assert r2.status_code == 201, r2.text

    detail = await client.get(f"/api/v1/materials/{mid}", headers=_h(owner))
    assert detail.status_code == 200, detail.text
    body = detail.json()
    # 2-decimal display rounding (Phase D).
    assert body["total_on_hand"] == "2000.00"
    assert body["weighted_avg_cost_per_gram"] == "0.03"
    assert body["on_hand_value"] == "60.00"
    # current_cost_per_gram mirrors weighted_avg_cost_per_gram (the
    # projection is the source of truth for both).
    assert Decimal(body["current_cost_per_gram"]) == Decimal("0.03")
