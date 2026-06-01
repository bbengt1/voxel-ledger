"""Product image upload / serve / delete (#259)."""

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

from tests._jobs_helpers import seed_product


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


def _png_bytes(color: str = "red") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (400, 300), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_serve_delete_roundtrip(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_root(app_session, tmp_path)
    owner = await _token(Role.OWNER, client, app_session)
    product = await seed_product(app_session, name="Imaged")

    # No image yet → 404.
    miss = await client.get(f"/api/v1/products/{product.id}/image", headers=_h(owner))
    assert miss.status_code == 404

    up = await client.post(
        f"/api/v1/products/{product.id}/image",
        headers=_h(owner),
        files={"file": ("pic.png", _png_bytes(), "image/png")},
    )
    assert up.status_code == 204, up.text

    # Both renditions serve as webp.
    for size in ("full", "thumb"):
        got = await client.get(
            f"/api/v1/products/{product.id}/image",
            headers=_h(owner),
            params={"size": size},
        )
        assert got.status_code == 200, got.text
        assert got.headers["content-type"] == "image/webp"
        assert len(got.content) > 0

    # Delete removes it.
    rm = await client.delete(f"/api/v1/products/{product.id}/image", headers=_h(owner))
    assert rm.status_code == 204
    after = await client.get(f"/api/v1/products/{product.id}/image", headers=_h(owner))
    assert after.status_code == 404


@pytest.mark.asyncio
async def test_rejects_non_image(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_root(app_session, tmp_path)
    owner = await _token(Role.OWNER, client, app_session)
    product = await seed_product(app_session, name="BadUpload")
    r = await client.post(
        f"/api/v1/products/{product.id}/image",
        headers=_h(owner),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_upload_unknown_product_404(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_root(app_session, tmp_path)
    owner = await _token(Role.OWNER, client, app_session)
    r = await client.post(
        f"/api/v1/products/{uuid.uuid4()}/image",
        headers=_h(owner),
        files={"file": ("pic.png", _png_bytes(), "image/png")},
    )
    assert r.status_code == 404, r.text
