"""Direct round-trip test for UUID-typed settings (#58).

Phase 3.2 (#56) added `inventory.default_receiving_location_id`, the
first UUID-typed setting in the registry. It's currently exercised only
indirectly via the material-receipt fallback flow. This test pins the
contract so future UUID-typed settings don't surprise anyone:

1. PUT a UUID via the settings endpoint succeeds.
2. GET returns the canonical 36-char UUID string (not a `{"hex": "..."}`
   wrapper or any pydantic-internal representation).
3. The persisted `setting.value` jsonb is the same string at the DB level.
4. PATCH (PUT again) replaces the value cleanly.
5. PUT with garbage rejects with 400.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from app.models.setting import Setting
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_uuid_setting_round_trip(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    await create_user(
        app_session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    token = await _login(client, "owner@example.com")

    target = workshop_location.id
    key = "inventory.default_receiving_location_id"

    # PUT
    put = await client.put(
        f"/api/v1/settings/{key}",
        headers=_h(token),
        json={"value": str(target)},
    )
    assert put.status_code == 200, put.text

    # GET
    got = await client.get(f"/api/v1/settings/{key}", headers=_h(token))
    assert got.status_code == 200
    body = got.json()
    assert body["value"] == str(target)
    # Canonical 36-char UUID, not a wrapped object.
    assert len(body["value"]) == 36
    # Parses back to a real UUID.
    assert uuid.UUID(body["value"]) == target

    # DB-level check: the persisted jsonb value is the canonical string.
    row = (await app_session.execute(select(Setting).where(Setting.key == key))).scalar_one()
    assert row.value == str(target)


@pytest.mark.asyncio
async def test_uuid_setting_replace(client: AsyncClient, app_session: AsyncSession) -> None:
    """PUT-ing a different UUID replaces the prior value."""
    from app.services import inventory_locations as locations_service

    loc_a = await locations_service.create(
        app_session,
        name="A",
        code="A",
        kind="workshop",
        actor_user_id=None,
    )
    loc_b = await locations_service.create(
        app_session,
        name="B",
        code="B",
        kind="workshop",
        actor_user_id=None,
    )
    await app_session.commit()

    await create_user(
        app_session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    token = await _login(client, "owner@example.com")

    key = "inventory.default_receiving_location_id"
    await client.put(
        f"/api/v1/settings/{key}",
        headers=_h(token),
        json={"value": str(loc_a.id)},
    )
    r = await client.put(
        f"/api/v1/settings/{key}",
        headers=_h(token),
        json={"value": str(loc_b.id)},
    )
    assert r.status_code == 200
    got = await client.get(f"/api/v1/settings/{key}", headers=_h(token))
    assert got.json()["value"] == str(loc_b.id)


@pytest.mark.asyncio
async def test_uuid_setting_rejects_garbage(client: AsyncClient, app_session: AsyncSession) -> None:
    await create_user(
        app_session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    token = await _login(client, "owner@example.com")

    r = await client.put(
        "/api/v1/settings/inventory.default_receiving_location_id",
        headers=_h(token),
        json={"value": "not-a-uuid"},
    )
    assert r.status_code in (400, 422), r.text
