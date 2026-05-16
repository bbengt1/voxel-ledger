"""Manual statement send endpoint (Phase 7.7, #115)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.settings.service import SettingsService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._invoices_helpers import auth_header, seed_customer, token_for


@pytest.mark.asyncio
async def test_send_statement_enqueues_statement_kind(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    # Use a writable storage root for body persistence.
    await SettingsService.set(
        "email.storage_root", str(tmp_path), session=app_session, actor_user_id=None
    )
    await app_session.commit()

    customer = await seed_customer(app_session, display_name="Acme")
    customer.primary_email = "acme@example.com"
    await app_session.commit()

    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        f"/api/v1/customers/{customer.id}/statements/send",
        headers=auth_header(token),
        json={"include_paid": False},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "statement"
    assert body["to_address"] == "acme@example.com"
    assert body["state"] == "queued"


@pytest.mark.asyncio
async def test_send_statement_requires_primary_email(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    await SettingsService.set(
        "email.storage_root", str(tmp_path), session=app_session, actor_user_id=None
    )
    await app_session.commit()
    customer = await seed_customer(app_session, display_name="No Email Co")
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        f"/api/v1/customers/{customer.id}/statements/send",
        headers=auth_header(token),
        json={"include_paid": False},
    )
    assert r.status_code == 400
    assert "primary_email" in r.text


@pytest.mark.asyncio
async def test_email_list_endpoint_filters(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    await SettingsService.set(
        "email.storage_root", str(tmp_path), session=app_session, actor_user_id=None
    )
    await app_session.commit()
    customer = await seed_customer(app_session, display_name="Acme")
    customer.primary_email = "acme@example.com"
    await app_session.commit()
    token = await token_for(Role.OWNER, client, app_session)
    await client.post(
        f"/api/v1/customers/{customer.id}/statements/send",
        headers=auth_header(token),
        json={"include_paid": False},
    )
    r = await client.get("/api/v1/email-messages?kind=statement", headers=auth_header(token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(i["kind"] == "statement" for i in items)
