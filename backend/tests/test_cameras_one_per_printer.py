"""Cameras: posting a second config to a printer that already has one
**replaces** the existing config (idempotent upsert). The DB enforces
``UNIQUE(printer_id)`` underneath; the service chose replace-semantics
over reject so callers can re-POST a form without first DELETEing.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(role: Role, client: AsyncClient, session: AsyncSession) -> str:
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


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_second_post_replaces_existing(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _login(Role.OWNER, client, app_session)
    pid = (
        await client.post(
            "/api/v1/printers",
            headers=_h(owner),
            json={"name": "P", "slug": "p1", "printer_type": "other"},
        )
    ).json()["id"]

    first = await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={
            "kind": "go2rtc",
            "snapshot_url": "http://a/snap.jpg",
        },
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["id"]

    second = await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={
            "kind": "rtsp",
            "snapshot_url": "http://b/snap.jpg",
        },
    )
    assert second.status_code == 200, second.text
    # Same row, mutated in place.
    assert second.json()["id"] == first_id
    assert second.json()["kind"] == "rtsp"
    assert second.json()["snapshot_url"] == "http://b/snap.jpg"

    # GET reflects the latest config — there is still exactly one.
    got = await client.get(f"/api/v1/printers/{pid}/cameras", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["id"] == first_id
    assert got.json()["kind"] == "rtsp"


@pytest.mark.asyncio
async def test_delete_then_post_creates_new_row(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _login(Role.OWNER, client, app_session)
    pid = (
        await client.post(
            "/api/v1/printers",
            headers=_h(owner),
            json={"name": "P", "slug": "p2", "printer_type": "other"},
        )
    ).json()["id"]

    a = await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={"kind": "go2rtc", "snapshot_url": "http://a/snap.jpg"},
    )
    aid = a.json()["id"]

    delr = await client.delete(f"/api/v1/printers/{pid}/cameras", headers=_h(owner))
    assert delr.status_code == 204

    b = await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={"kind": "go2rtc", "snapshot_url": "http://b/snap.jpg"},
    )
    assert b.status_code == 200
    # New row after DELETE.
    assert b.json()["id"] != aid
