"""Custom-fields events surface correctly in the audit log."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner_token(client: AsyncClient, session: AsyncSession) -> str:
    email = "owner@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="owner",
        role=Role.OWNER,
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
async def test_custom_field_create_archive_emits_events(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _owner_token(client, app_session)
    cf = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "supplier_code",
            "label": "Supplier Code",
            "field_type": "string",
        },
    )
    cf_id = cf.json()["id"]
    await client.post(f"/api/v1/custom-fields/{cf_id}/archive", headers=_h(owner))

    audit = await client.get(
        "/api/v1/admin/audit-log?event_type=platform.CustomFieldCreated",
        headers=_h(owner),
    )
    assert audit.status_code == 200, audit.text
    items = audit.json()["items"]
    assert any("supplier_code" in (it.get("summary") or "") for it in items)


@pytest.mark.asyncio
async def test_form_template_default_event(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _owner_token(client, app_session)
    t = await client.post(
        "/api/v1/form-templates",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "name": "Default",
            "is_default_for_entity_type": True,
        },
    )
    assert t.status_code == 201, t.text

    audit = await client.get(
        "/api/v1/admin/audit-log?event_type=platform.FormTemplateDefaulted",
        headers=_h(owner),
    )
    assert audit.status_code == 200
    assert audit.json()["items"], "expected a FormTemplateDefaulted event"
