"""Attachments upload: happy path, mime allowlist, size limit."""

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


async def _set_storage_root(session: AsyncSession, path: Path) -> None:
    await SettingsService.set(
        "attachments.storage_root",
        str(path),
        session=session,
        actor_user_id=None,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_happy_upload(client: AsyncClient, app_session: AsyncSession, tmp_path: Path) -> None:
    await _set_storage_root(app_session, tmp_path)
    owner = await _token_for(Role.OWNER, client, app_session)

    entity_id = str(uuid.uuid4())
    files = {
        "file": ("hello.txt", b"hello world", "text/plain"),
    }
    data = {"entity_kind": "material", "entity_id": entity_id}
    r = await client.post(
        "/api/v1/attachments",
        headers=_h(owner),
        data=data,
        files=files,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "hello.txt"
    assert body["mime_type"] == "text/plain"
    assert body["byte_size"] == 11
    # The file actually landed on disk under YYYY/MM/...
    files_on_disk = list(tmp_path.rglob("*"))
    assert any(p.is_file() and p.read_bytes() == b"hello world" for p in files_on_disk)


@pytest.mark.asyncio
async def test_viewer_cannot_upload(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_storage_root(app_session, tmp_path)
    tok = await _token_for(Role.VIEWER, client, app_session)
    files = {"file": ("hi.txt", b"x", "text/plain")}
    data = {"entity_kind": "material", "entity_id": str(uuid.uuid4())}
    r = await client.post(
        "/api/v1/attachments",
        headers=_h(tok),
        data=data,
        files=files,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_disallowed_mime_rejected_415(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_storage_root(app_session, tmp_path)
    owner = await _token_for(Role.OWNER, client, app_session)
    files = {"file": ("evil.exe", b"\x4d\x5a", "application/x-msdownload")}
    data = {"entity_kind": "material", "entity_id": str(uuid.uuid4())}
    r = await client.post(
        "/api/v1/attachments",
        headers=_h(owner),
        data=data,
        files=files,
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_oversize_rejected_413(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_storage_root(app_session, tmp_path)
    owner = await _token_for(Role.OWNER, client, app_session)
    # 10 MB + 1
    big = b"a" * (10 * 1024 * 1024 + 1)
    files = {"file": ("big.txt", big, "text/plain")}
    data = {"entity_kind": "material", "entity_id": str(uuid.uuid4())}
    r = await client.post(
        "/api/v1/attachments",
        headers=_h(owner),
        data=data,
        files=files,
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_allowed_image_and_pdf(
    client: AsyncClient, app_session: AsyncSession, tmp_path: Path
) -> None:
    await _set_storage_root(app_session, tmp_path)
    owner = await _token_for(Role.OWNER, client, app_session)
    entity_id = str(uuid.uuid4())
    for filename, mime in [
        ("pic.png", "image/png"),
        ("doc.pdf", "application/pdf"),
        (
            "spreadsheet.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        ("note.md", "text/markdown"),
    ]:
        r = await client.post(
            "/api/v1/attachments",
            headers=_h(owner),
            data={"entity_kind": "material", "entity_id": entity_id},
            files={"file": (filename, b"payload", mime)},
        )
        assert r.status_code == 201, (filename, r.text)
