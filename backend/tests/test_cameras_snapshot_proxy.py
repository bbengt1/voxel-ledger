"""Snapshot proxy: upstream HTTP is mocked via ``httpx.MockTransport``;
the proxy returns the bytes; the 2-second cache means two near-instant
requests hit the upstream only once.

Also covers 501 for kinds other than ``go2rtc``.
"""

from __future__ import annotations

import httpx
import pytest
from app.models.auth import Role
from app.services import cameras as cameras_service
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


JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"FAKE_JPEG_BODY" + b"\xff\xd9"


@pytest.fixture(autouse=True)
def _clear_snapshot_cache_between_tests():
    cameras_service._clear_snapshot_cache()
    cameras_service._set_test_transport(None)
    yield
    cameras_service._clear_snapshot_cache()
    cameras_service._set_test_transport(None)


@pytest.mark.asyncio
async def test_go2rtc_snapshot_returns_bytes_and_caches(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _login(Role.OWNER, client, app_session)
    pid = (
        await client.post(
            "/api/v1/printers",
            headers=_h(owner),
            json={"name": "P", "slug": "snap", "printer_type": "other"},
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={
            "kind": "go2rtc",
            "snapshot_url": "http://camera.local/api/frame.jpeg",
            "username": "u",
            "password_secret": "p",
        },
    )

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=JPEG_BYTES, headers={"Content-Type": "image/jpeg"})

    cameras_service._set_test_transport(httpx.MockTransport(handler))

    r1 = await client.get(f"/api/v1/printers/{pid}/cameras/snapshot.jpg", headers=_h(owner))
    assert r1.status_code == 200, r1.text
    assert r1.headers["content-type"].startswith("image/jpeg")
    assert r1.content == JPEG_BYTES
    assert r1.headers.get("cache-control") == "max-age=2, must-revalidate"
    assert len(calls) == 1
    # Basic auth applied when both username + password are present.
    assert calls[0].headers.get("authorization", "").lower().startswith("basic ")

    # Second request hits the cache — upstream is NOT called again.
    r2 = await client.get(f"/api/v1/printers/{pid}/cameras/snapshot.jpg", headers=_h(owner))
    assert r2.status_code == 200
    assert r2.content == JPEG_BYTES
    assert len(calls) == 1, "second request should be served from cache"


@pytest.mark.asyncio
async def test_non_go2rtc_returns_501(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _login(Role.OWNER, client, app_session)
    pid = (
        await client.post(
            "/api/v1/printers",
            headers=_h(owner),
            json={"name": "P", "slug": "snap501", "printer_type": "other"},
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/printers/{pid}/cameras",
        headers=_h(owner),
        json={"kind": "wyze", "snapshot_url": "http://nope/snap.jpg"},
    )

    r = await client.get(f"/api/v1/printers/{pid}/cameras/snapshot.jpg", headers=_h(owner))
    assert r.status_code == 501
