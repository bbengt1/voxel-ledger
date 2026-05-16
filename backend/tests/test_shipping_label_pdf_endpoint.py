"""``GET /api/v1/shipments/{id}/label.pdf`` (Phase 6.6, #98).

Asserts the endpoint streams the PDF bytes when a label has been
purchased and 404s when either the shipment doesn't exist or the
storage key is missing.
"""

from __future__ import annotations

import os
import uuid

from app.models.auth import Role
from app.services import shipping as shipping_service
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import auth_header, token_for
from tests._shipping_helpers import (
    SHIP_TO_FIXTURE,
    seed_draft_sale,
    seed_shipping_settings,
)


async def test_label_pdf_streams_for_purchased_label(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=250,
        dimensions_cm=None,
        service_level=None,
        carrier_hint="static_fallback",
        session=app_session,
    )
    await app_session.commit()
    await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()

    token = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/shipments/{shipment.id}/label.pdf",
        headers=auth_header(token),
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 100


async def test_label_pdf_404_for_missing_shipment(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    await seed_shipping_settings(app_session)
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/shipments/{uuid.uuid4()}/label.pdf",
        headers=auth_header(token),
    )
    assert r.status_code == 404


async def test_label_pdf_404_when_label_not_purchased(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    """Shipment exists but no label has been bought yet."""
    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=250,
        dimensions_cm=None,
        service_level=None,
        carrier_hint="static_fallback",
        session=app_session,
    )
    await app_session.commit()

    token = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/shipments/{shipment.id}/label.pdf",
        headers=auth_header(token),
    )
    assert r.status_code == 404


async def test_label_pdf_404_when_storage_file_missing(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    """We persisted a storage key on the row but the on-disk file is
    gone — the endpoint should 404 rather than 500."""
    tmp_root = await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=250,
        dimensions_cm=None,
        service_level=None,
        carrier_hint="static_fallback",
        session=app_session,
    )
    await app_session.commit()
    await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()

    # Delete the underlying file.
    pdf_path = os.path.join(tmp_root, "shipping-labels", f"{shipment.id}.pdf")
    assert os.path.isfile(pdf_path)
    os.remove(pdf_path)

    token = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/shipments/{shipment.id}/label.pdf",
        headers=auth_header(token),
    )
    assert r.status_code == 404
