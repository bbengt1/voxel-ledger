"""Phase 5.4 invariant: bogus Moonraker URLs MUST NOT crash the app.

Boot the app with two printers configured against unreachable hosts;
the app stays healthy, and the live-state endpoint returns either 503
``monitor_warming_up`` or 200 with ``state="disconnected"``.
"""

from __future__ import annotations

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
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "pw-correct"},
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_app_healthy_with_bogus_moonraker_urls(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    # Pin the probe to always fail — simulates an unreachable Moonraker
    # without paying real network timeouts in CI. The invariant under
    # test is "the app stays healthy", not "httpx times out cleanly".
    async def failing_probe(_u: str, _k: str | None) -> ProbeResult:
        return ProbeResult(ok=False)

    monitor_module.set_probe_factory(failing_probe)

    # Seed two printers pointing at unreachable hosts.
    p1 = await printers_service.create(
        app_session,
        name="Bogus 1",
        slug="bogus-1",
        printer_type="prusa_mk4",
        moonraker_url="http://127.0.0.1:1",
        actor_user_id=None,
    )
    p2 = await printers_service.create(
        app_session,
        name="Bogus 2",
        slug="bogus-2",
        printer_type="bambu_x1c",
        moonraker_url="http://no-such-host.invalid",
        actor_user_id=None,
    )
    await app_session.commit()

    # App stays healthy.
    h = await client.get("/health")
    assert h.status_code == 200

    token = await _owner_token(client, app_session)
    headers = {"Authorization": f"Bearer {token}"}

    for pid in (p1.id, p2.id):
        r = await client.get(f"/api/v1/printers/{pid}/state", headers=headers)
        assert r.status_code in (200, 503), r.text
        if r.status_code == 200:
            assert r.json()["state"] == "disconnected"
        else:
            assert r.json()["detail"] == "monitor_warming_up"
            assert r.headers.get("Retry-After") == "5"

    # And /health still works.
    h2 = await client.get("/health")
    assert h2.status_code == 200
