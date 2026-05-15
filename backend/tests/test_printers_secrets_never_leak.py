"""Regression: ``moonraker_api_key`` and ``password_secret`` MUST NOT
appear in any response body, in any event payload excerpt, or in any
summary string on the audit log.

This is the headline test for Phase 5.1's security invariant.
"""

from __future__ import annotations

import json

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

PRINTER_SECRET = "HUNTER2_DO_NOT_LEAK"
CAMERA_SECRET = "WYZE_PASSWORD_DO_NOT_LEAK"


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
async def test_moonraker_api_key_never_leaks(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _login(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/printers",
        headers=_h(owner),
        json={
            "name": "Leak test",
            "slug": "leak-test",
            "printer_type": "prusa_mk4",
            "moonraker_api_key": PRINTER_SECRET,
        },
    )
    assert create.status_code == 201, create.text
    pid = create.json()["id"]
    # Create response excludes the secret entirely.
    assert PRINTER_SECRET not in create.text
    assert create.json()["moonraker_api_key_set"] is True
    assert "moonraker_api_key" not in create.json()

    # GET back — still no leak.
    got = await client.get(f"/api/v1/printers/{pid}", headers=_h(owner))
    assert got.status_code == 200
    assert PRINTER_SECRET not in got.text
    assert got.json()["moonraker_api_key_set"] is True

    # Rotate the key via PATCH — diff event must use the sentinel, not
    # the new value.
    new_key = "ANOTHER_HUNTER2_VALUE"
    patched = await client.patch(
        f"/api/v1/printers/{pid}",
        headers=_h(owner),
        json={"moonraker_api_key": new_key},
    )
    assert patched.status_code == 200, patched.text
    assert new_key not in patched.text
    assert PRINTER_SECRET not in patched.text

    # Audit log must never contain either value.
    r = await client.get(
        "/api/v1/admin/audit-log",
        headers=_h(owner),
        params={"limit": 200},
    )
    assert r.status_code == 200
    body_text = r.text
    assert PRINTER_SECRET not in body_text
    assert new_key not in body_text
    # And no row has either value buried in payload_excerpt JSON.
    for row in r.json()["items"]:
        excerpt = row.get("payload_excerpt") or {}
        flat = json.dumps(excerpt)
        assert PRINTER_SECRET not in flat
        assert new_key not in flat


@pytest.mark.asyncio
async def test_camera_password_secret_never_leaks(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _login(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/printers",
        headers=_h(owner),
        json={"name": "Cam host", "slug": "cam-host", "printer_type": "other"},
    )
    pid = create.json()["id"]

    cam = await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={
            "kind": "go2rtc",
            "snapshot_url": "http://10.0.0.42/snapshot.jpg",
            "username": "wyze",
            "password_secret": CAMERA_SECRET,
        },
    )
    assert cam.status_code == 200, cam.text
    assert CAMERA_SECRET not in cam.text
    assert cam.json()["password_secret_set"] is True
    assert "password_secret" not in cam.json()

    got = await client.get(f"/api/v1/printers/{pid}/cameras", headers=_h(owner))
    assert got.status_code == 200
    assert CAMERA_SECRET not in got.text

    # Rotate.
    new_pw = "ANOTHER_PASSWORD_TO_HIDE"
    rotated = await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={
            "kind": "go2rtc",
            "snapshot_url": "http://10.0.0.42/snapshot.jpg",
            "username": "wyze",
            "password_secret": new_pw,
        },
    )
    assert rotated.status_code == 200
    assert new_pw not in rotated.text
    assert CAMERA_SECRET not in rotated.text

    r = await client.get(
        "/api/v1/admin/audit-log",
        headers=_h(owner),
        params={"limit": 200},
    )
    assert r.status_code == 200
    body_text = r.text
    assert CAMERA_SECRET not in body_text
    assert new_pw not in body_text
    for row in r.json()["items"]:
        excerpt = row.get("payload_excerpt") or {}
        flat = json.dumps(excerpt)
        assert CAMERA_SECRET not in flat
        assert new_pw not in flat
