"""Attachments archive: soft-delete preserves file; list filter works."""

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
async def test_archive_preserves_disk_and_hides_from_default_list(
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

    entity_id = str(uuid.uuid4())
    up = await client.post(
        "/api/v1/attachments",
        headers=_h(owner),
        data={"entity_kind": "material", "entity_id": entity_id},
        files={"file": ("doc.txt", b"keep", "text/plain")},
    )
    aid = up.json()["id"]
    on_disk = next(p for p in tmp_path.rglob("*") if p.is_file())

    arch = await client.post(f"/api/v1/attachments/{aid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    # File still on disk.
    assert on_disk.exists()
    assert on_disk.read_bytes() == b"keep"

    # Default list excludes archived.
    default = await client.get(
        f"/api/v1/attachments?entity_kind=material&entity_id={entity_id}",
        headers=_h(owner),
    )
    assert default.json()["items"] == []

    inc = await client.get(
        f"/api/v1/attachments?entity_kind=material&entity_id={entity_id}&include_archived=true",
        headers=_h(owner),
    )
    assert len(inc.json()["items"]) == 1
    assert inc.json()["items"][0]["is_archived"] is True


@pytest.mark.asyncio
async def test_non_uploader_non_owner_cannot_archive(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await SettingsService.set(
        "attachments.storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()
    uploader = await _token_for(Role.PRODUCTION, client, app_session)
    other = await _token_for(Role.SALES, client, app_session)
    up = await client.post(
        "/api/v1/attachments",
        headers=_h(uploader),
        data={"entity_kind": "material", "entity_id": str(uuid.uuid4())},
        files={"file": ("doc.txt", b"k", "text/plain")},
    )
    aid = up.json()["id"]

    r = await client.post(f"/api/v1/attachments/{aid}/archive", headers=_h(other))
    assert r.status_code == 403
