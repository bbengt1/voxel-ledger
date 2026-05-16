"""Bill PDF endpoint (Phase 8.2, #129)."""

from __future__ import annotations

import pytest

reportlab = pytest.importorskip("reportlab")

from app.models.auth import Role  # noqa: E402
from app.services.settings.service import SettingsService  # noqa: E402
from httpx import AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from tests._bills_helpers import (  # noqa: E402
    auth_header,
    sample_bill_body,
    seed_vendor,
    token_for,
)


@pytest.mark.asyncio
async def test_bill_pdf_renders_and_caches(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await SettingsService.set(
        "bills.pdf_storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    vendor = await seed_vendor(app_session)
    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    bill_id = create.json()["id"]

    r = await client.get(f"/api/v1/bills/{bill_id}/pdf", headers=auth_header(owner))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 100
    assert r.content.startswith(b"%PDF")

    r2 = await client.get(f"/api/v1/bills/{bill_id}/pdf", headers=auth_header(owner))
    assert r2.status_code == 200
    assert r2.content == r.content


@pytest.mark.asyncio
async def test_pdf_404_for_unknown_bill(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await SettingsService.set(
        "bills.pdf_storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()

    r = await client.get(
        "/api/v1/bills/00000000-0000-0000-0000-000000000000/pdf",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_pdf_requires_authenticated_role(
    client: AsyncClient, app_session: AsyncSession, tmp_path
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await SettingsService.set(
        "bills.pdf_storage_root",
        str(tmp_path),
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()
    vendor = await seed_vendor(app_session)
    create = await client.post(
        "/api/v1/bills",
        headers=auth_header(owner),
        json=sample_bill_body(vendor_id=str(vendor.id)),
    )
    bill_id = create.json()["id"]

    r = await client.get(f"/api/v1/bills/{bill_id}/pdf")
    assert r.status_code == 401
