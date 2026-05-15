"""Endpoint tests for GET /api/v1/printers/{id}/state (Phase 5.4)."""

from __future__ import annotations

import asyncio
import contextlib

import pytest
from app.models.auth import Role
from app.services import printers as printers_service
from app.services.auth import create_user
from app.services.printer_monitor import monitor as monitor_module
from app.services.printer_monitor.monitor import ProbeResult
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
async def _reset_monitor():
    """Each test gets a fresh monitor singleton + lock."""
    monitor_module._monitor = None
    monitor_module._monitor_lock = None
    monitor_module._probe_factory = monitor_module._default_probe
    yield
    if monitor_module._monitor is not None:
        with contextlib.suppress(Exception):
            await monitor_module._monitor.stop()
    monitor_module._monitor = None
    monitor_module._monitor_lock = None
    monitor_module._probe_factory = monitor_module._default_probe


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


@pytest.mark.asyncio
async def test_requires_auth(client: AsyncClient, app_session: AsyncSession) -> None:
    p = await printers_service.create(
        app_session,
        name="P1",
        slug="p1",
        printer_type="prusa_mk4",
        moonraker_url="http://stub.invalid",
        actor_user_id=None,
    )
    await app_session.commit()
    r = await client.get(f"/api/v1/printers/{p.id}/state")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_state_returns_200_after_probe(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Stub the probe to return a successful idle snapshot; the
    endpoint should hand back the cached state."""

    async def probe(_url: str, _key: str | None) -> ProbeResult:
        return ProbeResult(
            ok=True,
            state="idle",
            progress_pct=0.0,
            extruder_temp=42.0,
            bed_temp=25.0,
        )

    monitor_module.set_probe_factory(probe)

    p = await printers_service.create(
        app_session,
        name="Mock",
        slug="mock",
        printer_type="prusa_mk4",
        moonraker_url="http://stub.invalid",
        actor_user_id=None,
    )
    await app_session.commit()

    token = await _token_for(Role.VIEWER, client, app_session)
    headers = {"Authorization": f"Bearer {token}"}

    # First call may 503 (monitor warming up); wait briefly and retry.
    for _ in range(20):
        r = await client.get(f"/api/v1/printers/{p.id}/state", headers=headers)
        if r.status_code == 200:
            break
        await asyncio.sleep(0.1)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "idle"
    assert body["temperatures"]["extruder"] == 42.0
    assert body["temperatures"]["bed"] == 25.0
    assert body["last_seen_at"] is not None


@pytest.mark.asyncio
async def test_state_404_for_unknown_printer(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    import uuid

    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/printers/{uuid.uuid4()}/state",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_state_503_for_unmonitored_printer(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """A printer with no moonraker_url is not in the monitor's task
    set; the endpoint returns 503 with Retry-After."""
    p = await printers_service.create(
        app_session,
        name="No URL",
        slug="no-url",
        printer_type="other",
        moonraker_url=None,
        actor_user_id=None,
    )
    await app_session.commit()

    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/printers/{p.id}/state",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503
    assert r.headers["Retry-After"] == "5"
