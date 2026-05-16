"""Invoice PDF endpoint (Phase 7.3, #111)."""

from __future__ import annotations

import pytest

reportlab = pytest.importorskip("reportlab")

from app.models.auth import Role  # noqa: E402
from app.services.settings.service import SettingsService  # noqa: E402
from httpx import AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from tests._invoices_helpers import (  # noqa: E402
    auth_header,
    sample_invoice_body,
    seed_customer,
    token_for,
)


@pytest.mark.asyncio
async def test_invoice_pdf_renders_and_caches(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    # Configure local PDF storage root to a tmp dir so we don't write under /srv.
    await SettingsService.set(
        "invoices.pdf_storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    customer = await seed_customer(app_session)
    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    invoice_id = create.json()["id"]

    r = await client.get(f"/api/v1/invoices/{invoice_id}/pdf", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 100
    assert r.content.startswith(b"%PDF")

    # Re-fetch should hit cached file.
    r2 = await client.get(f"/api/v1/invoices/{invoice_id}/pdf", headers=auth_header(owner))
    assert r2.status_code == 200
    assert r2.content == r.content


@pytest.mark.asyncio
async def test_pdf_404_for_unknown_invoice(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await SettingsService.set(
        "invoices.pdf_storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    r = await client.get(
        "/api/v1/invoices/00000000-0000-0000-0000-000000000000/pdf",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_pdf_requires_authenticated_role(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await SettingsService.set(
        "invoices.pdf_storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()
    customer = await seed_customer(app_session)
    create = await client.post(
        "/api/v1/invoices",
        headers=auth_header(owner),
        json=sample_invoice_body(customer_id=str(customer.id)),
    )
    invoice_id = create.json()["id"]

    r = await client.get(f"/api/v1/invoices/{invoice_id}/pdf")
    assert r.status_code == 401
