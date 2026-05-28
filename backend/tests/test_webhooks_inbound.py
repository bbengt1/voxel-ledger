"""Inbound webhooks tests (Phase 11.2, #194)."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from app.models.shipment import Shipment, ShipmentState
from app.models.webhook_inbound import WebhookInboundEvent, WebhookInboundStatus
from app.services.settings.service import SettingsService
from app.services.webhooks import inbound as inbound_service
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._shipping_helpers import (
    SHIP_FROM_FIXTURE,
    SHIP_TO_FIXTURE,
    seed_draft_sale,
)

CARRIER_SECRET = "shh-easypost-shared"
SHIPSTATION_SECRET = "shh-shipstation"
MARKETPLACE_SECRET = "shh-marketplace"


async def _seed_secrets(app_session: AsyncSession) -> None:
    await SettingsService.set(
        "webhooks.inbound.carrier.easypost.secret",
        CARRIER_SECRET,
        session=app_session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "webhooks.inbound.carrier.shipstation.secret",
        SHIPSTATION_SECRET,
        session=app_session,
        actor_user_id=None,
    )
    await SettingsService.set(
        "webhooks.inbound.marketplace.etsy.secret",
        MARKETPLACE_SECRET,
        session=app_session,
        actor_user_id=None,
    )
    await app_session.commit()


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _easypost_body(*, tracking: str = "TRK-EXAMPLE-1", event_id: str = "evt_1") -> bytes:
    payload = {
        "id": event_id,
        "description": "tracker.updated",
        "result": {
            "id": "trk_1",
            "tracking_code": tracking,
            "status": "delivered",
            "status_detail": "arrived_at_destination",
            "updated_at": "2026-05-20T10:00:00Z",
        },
    }
    return json.dumps(payload).encode("utf-8")


# ---------------------------------------------------------------------------
# unit: verifiers
# ---------------------------------------------------------------------------


def test_verify_easypost_accepts_valid_signature() -> None:
    body = b'{"hello":"world"}'
    sig = _sign(CARRIER_SECRET, body)
    inbound_service.verify_easypost(
        secret=CARRIER_SECRET,
        body=body,
        headers={"X-Hmac-Signature": f"sha256={sig}"},
    )


def test_verify_easypost_rejects_bad_signature() -> None:
    with pytest.raises(inbound_service.InvalidSignatureError):
        inbound_service.verify_easypost(
            secret=CARRIER_SECRET,
            body=b'{"hello":"world"}',
            headers={"X-Hmac-Signature": "sha256=deadbeef"},
        )


def test_verify_easypost_missing_header() -> None:
    with pytest.raises(inbound_service.InvalidSignatureError):
        inbound_service.verify_easypost(secret=CARRIER_SECRET, body=b"x", headers={})


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_carrier_bad_signature_returns_401(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_secrets(app_session)
    body = _easypost_body()
    resp = await client.post(
        "/api/v1/webhooks/inbound/carriers/easypost",
        content=body,
        headers={"X-Hmac-Signature": "sha256=00", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_carrier_unknown_provider_404(client: AsyncClient, app_session: AsyncSession) -> None:
    await _seed_secrets(app_session)
    resp = await client.post(
        "/api/v1/webhooks/inbound/carriers/madeup",
        content=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_carrier_unknown_tracking_records_unmatched(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_secrets(app_session)
    body = _easypost_body(tracking="NO-MATCH", event_id="evt_unmatched")
    sig = _sign(CARRIER_SECRET, body)
    resp = await client.post(
        "/api/v1/webhooks/inbound/carriers/easypost",
        content=body,
        headers={
            "X-Hmac-Signature": f"sha256={sig}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    body_json = resp.json()
    assert body_json["status"] == "unmatched"

    row = (
        await app_session.execute(
            select(WebhookInboundEvent).where(
                WebhookInboundEvent.external_event_id == "evt_unmatched"
            )
        )
    ).scalar_one()
    assert row.status == WebhookInboundStatus.UNMATCHED


@pytest.mark.asyncio
async def test_carrier_idempotent_on_external_event_id(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_secrets(app_session)
    body = _easypost_body(event_id="evt_dup")
    sig = _sign(CARRIER_SECRET, body)
    hdrs = {
        "X-Hmac-Signature": f"sha256={sig}",
        "Content-Type": "application/json",
    }

    first = await client.post(
        "/api/v1/webhooks/inbound/carriers/easypost", content=body, headers=hdrs
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/webhooks/inbound/carriers/easypost", content=body, headers=hdrs
    )
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["id"] == first.json()["id"]

    # Only one row exists.
    rows = (
        (
            await app_session.execute(
                select(WebhookInboundEvent).where(
                    WebhookInboundEvent.external_event_id == "evt_dup"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_carrier_applies_to_matching_shipment(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_secrets(app_session)

    sale = await seed_draft_sale(app_session)
    shipment = Shipment(
        id=uuid.uuid4(),
        sale_id=sale.id,
        carrier="easypost",
        state=ShipmentState.SHIPPED,
        tracking_number="TRK-DELIVERED-1",
        ship_from=dict(SHIP_FROM_FIXTURE),
        ship_to=dict(SHIP_TO_FIXTURE),
    )
    app_session.add(shipment)
    await app_session.commit()

    body = _easypost_body(tracking="TRK-DELIVERED-1", event_id="evt_apply")
    sig = _sign(CARRIER_SECRET, body)
    resp = await client.post(
        "/api/v1/webhooks/inbound/carriers/easypost",
        content=body,
        headers={
            "X-Hmac-Signature": f"sha256={sig}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"

    # The inbound row itself records ``applied`` (with applied_at set);
    # checking it on the test session is enough to prove the wire-up.
    # The shipment-state mutation is exercised directly by the unit
    # test of :func:`apply_tracking_update` below.
    row = (
        await app_session.execute(
            select(WebhookInboundEvent).where(WebhookInboundEvent.external_event_id == "evt_apply")
        )
    ).scalar_one()
    assert row.status == WebhookInboundStatus.APPLIED
    assert row.applied_at is not None


@pytest.mark.asyncio
async def test_apply_tracking_update_unit(app_session: AsyncSession) -> None:
    sale = await seed_draft_sale(app_session)
    shipment = Shipment(
        id=uuid.uuid4(),
        sale_id=sale.id,
        carrier="easypost",
        state=ShipmentState.SHIPPED,
        tracking_number="UNIT-TRK-1",
        ship_from=dict(SHIP_FROM_FIXTURE),
        ship_to=dict(SHIP_TO_FIXTURE),
    )
    app_session.add(shipment)
    await app_session.commit()

    result = await inbound_service.apply_tracking_update(
        app_session,
        inbound_service.CarrierTrackingUpdate(
            tracking_number="UNIT-TRK-1",
            status="delivered",
            status_detail=None,
            event_at=None,
        ),
    )
    assert result is not None
    assert shipment.state == ShipmentState.DELIVERED


# ---------------------------------------------------------------------------
# marketplace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_marketplace_stages_event(client: AsyncClient, app_session: AsyncSession) -> None:
    await _seed_secrets(app_session)
    body = json.dumps(
        {
            "event_id": "mp_evt_1",
            "type": "order.created",
            "order_id": "ORDER-1",
            "total": "12.34",
        }
    ).encode("utf-8")
    sig = _sign(MARKETPLACE_SECRET, body)
    resp = await client.post(
        "/api/v1/webhooks/inbound/marketplaces/etsy",
        content=body,
        headers={
            "X-Marketplace-Signature": f"sha256={sig}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"

    row = (
        await app_session.execute(
            select(WebhookInboundEvent).where(WebhookInboundEvent.external_event_id == "mp_evt_1")
        )
    ).scalar_one()
    assert row.payload["order_id"] == "ORDER-1"


@pytest.mark.asyncio
async def test_marketplace_unknown_provider_404(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_secrets(app_session)
    resp = await client.post(
        "/api/v1/webhooks/inbound/marketplaces/madeup",
        content=b"{}",
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_missing_secret_returns_401(client: AsyncClient, app_session: AsyncSession) -> None:
    # No secrets seeded - even a "valid" signature is rejected because
    # the server has no key to verify against.
    body = _easypost_body()
    sig = _sign("guess", body)
    resp = await client.post(
        "/api/v1/webhooks/inbound/carriers/easypost",
        content=body,
        headers={
            "X-Hmac-Signature": f"sha256={sig}",
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401
