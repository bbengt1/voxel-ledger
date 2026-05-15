"""Admin endpoint: POST /api/v1/admin/printer-monitor/restart (Phase 5.4)."""

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
async def test_requires_auth(client: AsyncClient) -> None:
    r = await client.post("/api/v1/admin/printer-monitor/restart")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected: int,
) -> None:
    async def probe(_u: str, _k: str | None) -> ProbeResult:
        return ProbeResult(ok=False)

    monitor_module.set_probe_factory(probe)

    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/admin/printer-monitor/restart",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_restart_is_idempotent(client: AsyncClient, app_session: AsyncSession) -> None:
    async def probe(_u: str, _k: str | None) -> ProbeResult:
        return ProbeResult(ok=True, state="idle")

    monitor_module.set_probe_factory(probe)

    await printers_service.create(
        app_session,
        name="R1",
        slug="r1",
        printer_type="prusa_mk4",
        moonraker_url="http://stub.invalid",
        actor_user_id=None,
    )
    await app_session.commit()

    token = await _token_for(Role.OWNER, client, app_session)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post("/api/v1/admin/printer-monitor/restart", headers=headers)
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["restarted"] is True
    assert body1["printers_monitored"] == 1

    # Second call: still works.
    r2 = await client.post("/api/v1/admin/printer-monitor/restart", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["printers_monitored"] == 1
