"""User-admin event emission + payload regression (Phase 1.6).

Each mutation emits the expected event type. Payloads MUST NOT contain
any password-shaped substrings — checked across the full event row JSON.
"""

from __future__ import annotations

import json

import pytest
from app.events.types import users as users_events
from app.models.auth import Role
from app.models.event import Event
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

FORBIDDEN_SUBSTRINGS = (
    "password",
    "password_hash",
    "passwd",
    "$2b$",  # bcrypt prefix
    "$2a$",
)


def _scan_for_passwords(events: list[Event]) -> None:
    for ev in events:
        if ev.type.startswith("auth."):
            # Auth events are out of scope here.
            continue
        as_json = json.dumps(ev.payload or {}).lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in as_json, (
                f"event {ev.type} payload contained forbidden substring "
                f"{needle!r}: {ev.payload!r}"
            )


@pytest.fixture
async def owner_token(client: AsyncClient, app_session: AsyncSession) -> str:
    await create_user(
        app_session,
        email="owner@example.com",
        password="pw-correct",
        full_name="O",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_create_emits_user_created(
    client: AsyncClient, app_session: AsyncSession, owner_token: str
) -> None:
    r = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "ev@example.com", "full_name": "E", "role": "sales"},
    )
    assert r.status_code == 201
    rows = (
        (
            await app_session.execute(
                select(Event).where(Event.type == users_events.TYPE_USER_CREATED)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    payload = rows[0].payload
    assert payload["email"] == "ev@example.com"
    assert payload["role"] == "sales"
    assert payload["full_name"] == "E"
    assert "password" not in json.dumps(payload).lower()


@pytest.mark.asyncio
async def test_update_emits_user_updated_with_diff(
    client: AsyncClient, app_session: AsyncSession, owner_token: str
) -> None:
    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "u@example.com", "full_name": "Orig", "role": "sales"},
    )
    uid = create.json()["user"]["id"]
    r = await client.patch(
        f"/api/v1/users/{uid}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"full_name": "New", "role": "production"},
    )
    assert r.status_code == 200, r.text
    rows = (
        (
            await app_session.execute(
                select(Event).where(Event.type == users_events.TYPE_USER_UPDATED)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    payload = rows[0].payload
    assert payload["before"]["full_name"] == "Orig"
    assert payload["after"]["full_name"] == "New"
    assert payload["before"]["role"] == "sales"
    assert payload["after"]["role"] == "production"


@pytest.mark.asyncio
async def test_deactivate_and_reactivate_emit_events(
    client: AsyncClient, app_session: AsyncSession, owner_token: str
) -> None:
    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "d@example.com", "full_name": "D", "role": "sales"},
    )
    uid = create.json()["user"]["id"]

    await client.post(
        f"/api/v1/users/{uid}/deactivate",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    await client.post(
        f"/api/v1/users/{uid}/reactivate",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    de = (
        (
            await app_session.execute(
                select(Event).where(Event.type == users_events.TYPE_USER_DEACTIVATED)
            )
        )
        .scalars()
        .all()
    )
    re = (
        (
            await app_session.execute(
                select(Event).where(Event.type == users_events.TYPE_USER_REACTIVATED)
            )
        )
        .scalars()
        .all()
    )
    assert len(de) == 1
    assert de[0].payload["reason"] == "admin_action"
    assert len(re) == 1


@pytest.mark.asyncio
async def test_reset_password_emits_event_with_no_secret(
    client: AsyncClient, app_session: AsyncSession, owner_token: str
) -> None:
    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "rp@example.com", "full_name": "RP", "role": "sales"},
    )
    uid = create.json()["user"]["id"]
    rp = await client.post(
        f"/api/v1/users/{uid}/reset-password",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    new_pwd = rp.json()["generated_password"]

    rows = (
        (
            await app_session.execute(
                select(Event).where(Event.type == users_events.TYPE_PASSWORD_RESET_BY_ADMIN)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    payload = rows[0].payload
    assert "password" not in json.dumps(payload).lower()
    # And concretely: the raw password we got back is NOT in the event.
    assert new_pwd not in json.dumps(payload)


@pytest.mark.asyncio
async def test_no_password_in_any_users_event(
    client: AsyncClient, app_session: AsyncSession, owner_token: str
) -> None:
    """Regression: across every users.* event, the payload must not
    contain a password-shaped substring."""
    create = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "x@example.com", "full_name": "X", "role": "sales"},
    )
    uid = create.json()["user"]["id"]
    await client.patch(
        f"/api/v1/users/{uid}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"full_name": "Y"},
    )
    await client.post(
        f"/api/v1/users/{uid}/deactivate",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    await client.post(
        f"/api/v1/users/{uid}/reactivate",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    await client.post(
        f"/api/v1/users/{uid}/reset-password",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    rows = (
        (await app_session.execute(select(Event).where(Event.type.like("users.%")))).scalars().all()
    )
    assert len(rows) >= 5
    _scan_for_passwords(list(rows))
