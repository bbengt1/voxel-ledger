"""Attachments: round-trip byte equality on download."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
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
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_download_roundtrip(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await SettingsService.set(
        "attachments.storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()
    owner = await _token_for(Role.OWNER, client, app_session)

    # Use binary content so we'd notice any text-mode munging.
    payload = bytes(range(256)) * 4
    files = {"file": ("blob.pdf", payload, "application/pdf")}
    data = {"entity_kind": "material", "entity_id": str(uuid.uuid4())}
    up = await client.post(
        "/api/v1/attachments",
        headers=_h(owner),
        data=data,
        files=files,
    )
    assert up.status_code == 201, up.text
    aid = up.json()["id"]

    # Now download and compare bytes.
    dn = await client.get(f"/api/v1/attachments/{aid}/download", headers=_h(owner))
    assert dn.status_code == 200
    assert dn.content == payload
    # Content-Disposition with filename.
    assert "filename=" in dn.headers.get("content-disposition", "")
    assert dn.headers.get("content-type", "").startswith("application/pdf")
