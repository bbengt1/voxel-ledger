"""Part image upload / serve / delete (epic #267 Phase 1; reuses entity_images)."""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession


async def _token(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-{uuid.uuid4().hex[:6]}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _set_root(session: AsyncSession, path: Path) -> None:
    await SettingsService.set(
        "attachments.storage_root", str(path), session=session, actor_user_id=None
    )
    await session.commit()


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (300, 200), "blue").save(buf, format="PNG")
    return buf.getvalue()


async def _make_part(client: AsyncClient, token: str) -> str:
    r = await client.post("/api/v1/parts", headers=_h(token), json={"name": "Imaged part"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_part_image_roundtrip(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_root(app_session, tmp_path)
    owner = await _token(Role.OWNER, client, app_session)
    part_id = await _make_part(client, owner)

    assert (
        await client.get(f"/api/v1/parts/{part_id}/image", headers=_h(owner))
    ).status_code == 404

    up = await client.post(
        f"/api/v1/parts/{part_id}/image",
        headers=_h(owner),
        files={"file": ("p.png", _png(), "image/png")},
    )
    assert up.status_code == 204, up.text

    for size in ("full", "thumb"):
        got = await client.get(
            f"/api/v1/parts/{part_id}/image", headers=_h(owner), params={"size": size}
        )
        assert got.status_code == 200
        assert got.headers["content-type"] == "image/webp"
        assert len(got.content) > 0

    rm = await client.delete(f"/api/v1/parts/{part_id}/image", headers=_h(owner))
    assert rm.status_code == 204
    assert (
        await client.get(f"/api/v1/parts/{part_id}/image", headers=_h(owner))
    ).status_code == 404


@pytest.mark.asyncio
async def test_part_image_rejects_non_image(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_root(app_session, tmp_path)
    owner = await _token(Role.OWNER, client, app_session)
    part_id = await _make_part(client, owner)
    r = await client.post(
        f"/api/v1/parts/{part_id}/image",
        headers=_h(owner),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400, r.text
