"""Parts support manual inventory adjustment + transfer via the HTTP API.

Parts are normally moved by jobs/builds, but on-hand corrections need a
manual path (adjustment / reconciliation) and stock can be relocated
(transfer). The write schema accepts ``entity_kind="part"`` and the
balances flow through to the part detail response.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner_token(client: AsyncClient, session: AsyncSession) -> str:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "pw-correct"}
    )
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _location(client: AsyncClient, h, name: str, code: str, kind: str = "workshop") -> dict:
    return (
        await client.post(
            "/api/v1/inventory/locations",
            headers=h,
            json={"name": name, "code": code, "kind": kind},
        )
    ).json()


async def _part(client: AsyncClient, h) -> dict:
    return (await client.post("/api/v1/parts", headers=h, json={"name": "Bracket"})).json()


@pytest.mark.asyncio
async def test_part_adjustment_moves_on_hand(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _owner_token(client, app_session)
    h = _h(owner)
    loc = await _location(client, h, "WS", "WS")
    part = await _part(client, h)

    # Positive adjustment of +5 (e.g. found stock during a count).
    r = await client.post(
        "/api/v1/inventory/transactions",
        headers=h,
        json={
            "kind": "adjustment",
            "entity_kind": "part",
            "entity_id": part["id"],
            "location_id": loc["id"],
            "quantity": "5",
            "reason": "reconcile: counted 5",
        },
    )
    assert r.status_code == 201, r.text

    detail = (await client.get(f"/api/v1/parts/{part['id']}", headers=h)).json()
    assert Decimal(detail["total_on_hand"]) == Decimal("5")
    assert Decimal(detail["per_location_on_hand"][loc["id"]]) == Decimal("5")

    # A negative adjustment (reconcile down) nets the balance.
    r2 = await client.post(
        "/api/v1/inventory/transactions",
        headers=h,
        json={
            "kind": "adjustment",
            "entity_kind": "part",
            "entity_id": part["id"],
            "location_id": loc["id"],
            "quantity": "-2",
        },
    )
    assert r2.status_code == 201, r2.text
    detail2 = (await client.get(f"/api/v1/parts/{part['id']}", headers=h)).json()
    assert Decimal(detail2["total_on_hand"]) == Decimal("3")


@pytest.mark.asyncio
async def test_part_transfer_between_locations(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _owner_token(client, app_session)
    h = _h(owner)
    loc_a = await _location(client, h, "A", "A")
    loc_b = await _location(client, h, "B", "B", kind="staging")
    part = await _part(client, h)

    # Seed 10 at A via an adjustment, then move 4 to B.
    await client.post(
        "/api/v1/inventory/transactions",
        headers=h,
        json={
            "kind": "adjustment",
            "entity_kind": "part",
            "entity_id": part["id"],
            "location_id": loc_a["id"],
            "quantity": "10",
        },
    )
    r = await client.post(
        "/api/v1/inventory/transactions/transfer",
        headers=h,
        json={
            "entity_kind": "part",
            "entity_id": part["id"],
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
            "quantity": "4",
        },
    )
    assert r.status_code in (200, 201), r.text

    detail = (await client.get(f"/api/v1/parts/{part['id']}", headers=h)).json()
    assert Decimal(detail["total_on_hand"]) == Decimal("10")
    assert Decimal(detail["per_location_on_hand"][loc_a["id"]]) == Decimal("6")
    assert Decimal(detail["per_location_on_hand"][loc_b["id"]]) == Decimal("4")
