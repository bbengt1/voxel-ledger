"""Phase 3.3 (#52) low-stock alerts and on-hand endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_low_stock_alert_surfaces_material(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    # Seed a workshop location and configure as default-receiving.
    loc = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(owner),
        json={"name": "Workshop", "code": "WS", "kind": "workshop"},
    )
    assert loc.status_code == 201, loc.text
    loc_id = loc.json()["id"]
    set_setting = await client.put(
        "/api/v1/settings/inventory.default_receiving_location_id",
        headers=_h(owner),
        json={"value": loc_id},
    )
    assert set_setting.status_code in (200, 204), set_setting.text

    # Create a material with threshold=100g.
    mat = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={
            "name": "PLA",
            "material_type": "PLA",
            "low_stock_threshold_grams": "100",
            "spool_weight_grams": 1000,
        },
    )
    assert mat.status_code == 201, mat.text
    mid = mat.json()["id"]

    # Receive 50g — below threshold.
    rec = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=_h(owner),
        json={"spools": 0, "extra_grams": "50", "price_per_spool": "200.00"},
    )
    assert rec.status_code == 201, rec.text

    alerts = await client.get("/api/v1/inventory/alerts/low-stock", headers=_h(owner))
    assert alerts.status_code == 200, alerts.text
    items = alerts.json()["items"]
    assert len(items) == 1
    assert items[0]["entity_kind"] == "material"
    assert items[0]["entity_id"] == mid
    assert Decimal(items[0]["threshold"]) == Decimal("100")
    assert Decimal(items[0]["total_on_hand"]) == Decimal("50")
    assert Decimal(items[0]["deficit"]) == Decimal("50")


@pytest.mark.asyncio
async def test_material_without_threshold_does_not_appear(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    mat = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "PLA", "material_type": "PLA", "spool_weight_grams": 1000},
    )
    assert mat.status_code == 201
    alerts = await client.get("/api/v1/inventory/alerts/low-stock", headers=_h(owner))
    assert alerts.status_code == 200
    assert alerts.json()["items"] == []


@pytest.mark.asyncio
async def test_alerts_sorted_by_deficit_desc(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    loc = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(owner),
        json={"name": "WS", "code": "WS", "kind": "workshop"},
    )
    loc_id = loc.json()["id"]
    await client.put(
        "/api/v1/settings/inventory.default_receiving_location_id",
        headers=_h(owner),
        json={"value": loc_id},
    )
    # Two materials, one with bigger deficit.
    m1 = (
        await client.post(
            "/api/v1/materials",
            headers=_h(owner),
            json={
                "name": "PLA-A",
                "material_type": "PLA",
                "low_stock_threshold_grams": "1000",
                "spool_weight_grams": 1000,
            },
        )
    ).json()["id"]
    m2 = (
        await client.post(
            "/api/v1/materials",
            headers=_h(owner),
            json={
                "name": "PLA-B",
                "material_type": "PLA",
                "low_stock_threshold_grams": "200",
                "spool_weight_grams": 1000,
            },
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/materials/{m1}/receipts",
        headers=_h(owner),
        json={"spools": 0, "extra_grams": "100", "price_per_spool": "10.00"},
    )
    await client.post(
        f"/api/v1/materials/{m2}/receipts",
        headers=_h(owner),
        json={"spools": 0, "extra_grams": "100", "price_per_spool": "10.00"},
    )
    body = (await client.get("/api/v1/inventory/alerts/low-stock", headers=_h(owner))).json()
    items = body["items"]
    assert [it["entity_id"] for it in items] == [m1, m2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.SALES, Role.PRODUCTION, Role.BOOKKEEPER, Role.VIEWER],
)
async def test_alerts_and_on_hand_open_to_every_role(
    client: AsyncClient, app_session: AsyncSession, role: Role
) -> None:
    token = await _token_for(role, client, app_session)
    r1 = await client.get("/api/v1/inventory/alerts/low-stock", headers=_h(token))
    r2 = await client.get("/api/v1/inventory/on-hand", headers=_h(token))
    assert r1.status_code == 200
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_on_hand_endpoint_returns_rows_and_summaries(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    loc = await client.post(
        "/api/v1/inventory/locations",
        headers=_h(owner),
        json={"name": "WS", "code": "WS", "kind": "workshop"},
    )
    loc_id = loc.json()["id"]
    mat = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "PLA", "material_type": "PLA", "spool_weight_grams": 1000},
    )
    mid = mat.json()["id"]
    # Adjustment to seed an on-hand row.
    r = await client.post(
        "/api/v1/inventory/transactions",
        headers=_h(owner),
        json={
            "kind": "adjustment",
            "entity_kind": "material",
            "entity_id": mid,
            "location_id": loc_id,
            "quantity": "25",
        },
    )
    assert r.status_code == 201, r.text
    body = (await client.get("/api/v1/inventory/on-hand", headers=_h(owner))).json()
    assert any(row["entity_id"] == mid for row in body["rows"])
    assert any(s["entity_id"] == mid for s in body["summaries"])
