"""Role gating for shipment endpoints (Phase 6.6, #98).

Spec: owner + sales + bookkeeper write; viewer reads only.
Production role has no shipping access (it owns the shop floor, not
fulfillment).
"""

from __future__ import annotations

import pytest
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

WRITE_ROLES = (Role.OWNER, Role.SALES, Role.BOOKKEEPER)
DENY_WRITE_ROLES = (Role.PRODUCTION, Role.VIEWER)


@pytest.mark.parametrize("role", WRITE_ROLES)
async def test_create_shipment_allowed_for_write_roles(
    role: Role,
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    token = await token_for(role, client, app_session)
    r = await client.post(
        f"/api/v1/sales/{sale.id}/shipments",
        headers=auth_header(token),
        json={
            "ship_to": SHIP_TO_FIXTURE,
            "weight_grams": 250,
            "carrier_hint": "static_fallback",
        },
    )
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("role", DENY_WRITE_ROLES)
async def test_create_shipment_denied_for_non_write_roles(
    role: Role,
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    token = await token_for(role, client, app_session)
    r = await client.post(
        f"/api/v1/sales/{sale.id}/shipments",
        headers=auth_header(token),
        json={"ship_to": SHIP_TO_FIXTURE},
    )
    assert r.status_code == 403, r.text


async def test_label_pdf_requires_write_role(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    """Spec: owner + sales + bookkeeper can download the label.

    Viewer is rejected because the label PDF carries the destination
    address (PII) and the viewer role is observational.
    """
    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=200,
        dimensions_cm=None,
        service_level=None,
        carrier_hint="static_fallback",
        session=app_session,
    )
    await app_session.commit()
    await shipping_service.purchase_label(shipment.id, session=app_session)
    await app_session.commit()

    # Viewer denied.
    v_token = await token_for(Role.VIEWER, client, app_session)
    r = await client.get(
        f"/api/v1/shipments/{shipment.id}/label.pdf",
        headers=auth_header(v_token),
    )
    assert r.status_code == 403, r.text

    # Owner OK.
    o_token = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/shipments/{shipment.id}/label.pdf",
        headers=auth_header(o_token),
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")


async def test_get_shipment_allows_viewer(
    client: AsyncClient,
    app_session: AsyncSession,
) -> None:
    """GET on the shipment row is read-only metadata (no PDF) and the
    spec opens that to the viewer role."""
    await seed_shipping_settings(app_session)
    sale = await seed_draft_sale(app_session)
    shipment = await shipping_service.create_shipment(
        sale.id,
        ship_to=SHIP_TO_FIXTURE,
        weight_grams=200,
        dimensions_cm=None,
        service_level=None,
        carrier_hint="static_fallback",
        session=app_session,
    )
    await app_session.commit()

    token = await token_for(Role.VIEWER, client, app_session)
    r = await client.get(
        f"/api/v1/shipments/{shipment.id}",
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
