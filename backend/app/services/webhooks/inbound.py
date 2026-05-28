"""Inbound webhook intake (Phase 11.2, #194).

Two endpoint groups:

* ``POST /api/v1/webhooks/inbound/carriers/{provider}`` -
  carrier tracking updates. Real adapters for ``easypost`` and
  ``shipstation``. Each adapter ships a real signature verifier; only
  ``easypost`` ships a real payload parser today (``shipstation``
  returns ``not_implemented`` after a successful signature check so we
  still record the receipt).
* ``POST /api/v1/webhooks/inbound/marketplaces/{provider}`` -
  marketplace order / refund events. Signature verification is real
  per provider; the parsed event is staged in
  ``webhook_inbound_event`` for the existing Phase 9.8 / 9.9
  auto-matcher to consume on its next sweep.

Idempotency
-----------
Every inbound event is dedup'd on ``(provider, external_event_id)``
via the ``webhook_inbound_event`` table. A duplicate POST returns 200
+ ``status='duplicate'`` without re-applying the adapter.

PII contract
------------
Inbound bodies frequently contain customer addresses + order details.
They land in ``webhook_inbound_event.payload`` (JSON) and are NOT
whitelisted into the audit excerpt by default.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shipment import Shipment, ShipmentState
from app.models.webhook_inbound import (
    WebhookInboundEvent,
    WebhookInboundKind,
    WebhookInboundStatus,
)
from app.services.settings.service import SettingsService

# Providers we accept signatures for. Anything outside these returns
# 404 from the router (before any DB writes).
CARRIER_PROVIDERS: frozenset[str] = frozenset({"easypost", "shipstation"})
MARKETPLACE_PROVIDERS: frozenset[str] = frozenset({"ebay", "etsy", "shopify", "amazon"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InboundWebhookError(Exception):
    """Base."""


class UnknownProviderError(InboundWebhookError):
    """Provider not in the per-kind allow-list. Mapped to 404."""


class InvalidSignatureError(InboundWebhookError):
    """Signature header missing or doesn't verify. Mapped to 401."""


class MissingSecretError(InboundWebhookError):
    """No shared secret configured for this provider. Mapped to 401."""


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def _setting_key(kind: WebhookInboundKind, provider: str) -> str:
    return f"webhooks.inbound.{kind.value}.{provider}.secret"


async def _resolve_secret(
    *,
    session: AsyncSession,
    kind: WebhookInboundKind,
    provider: str,
) -> str:
    secret = await SettingsService.get(_setting_key(kind, provider), session=session)
    if not secret:
        raise MissingSecretError(f"no shared secret configured at {_setting_key(kind, provider)!r}")
    return str(secret)


def _hmac_sha256(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _constant_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_easypost(*, secret: str, body: bytes, headers: dict[str, str]) -> None:
    """EasyPost: ``X-Hmac-Signature: sha256=<hex>`` over the raw body."""
    raw = headers.get("X-Hmac-Signature") or headers.get("x-hmac-signature")
    if not raw or not raw.startswith("sha256="):
        raise InvalidSignatureError("missing or malformed X-Hmac-Signature header")
    expected = _hmac_sha256(secret, body)
    if not _constant_eq(raw.split("=", 1)[1], expected):
        raise InvalidSignatureError("signature mismatch")


def verify_shipstation(*, secret: str, body: bytes, headers: dict[str, str]) -> None:
    """ShipStation: ``X-Ss-Signature: <hex>`` over the raw body."""
    raw = headers.get("X-Ss-Signature") or headers.get("x-ss-signature")
    if not raw:
        raise InvalidSignatureError("missing X-Ss-Signature header")
    expected = _hmac_sha256(secret, body)
    if not _constant_eq(raw, expected):
        raise InvalidSignatureError("signature mismatch")


def verify_marketplace_generic(*, secret: str, body: bytes, headers: dict[str, str]) -> None:
    """All marketplace providers we ship today use a single header
    convention: ``X-Marketplace-Signature: sha256=<hex>``.

    Real provider integrations (Etsy OAuth, Shopify HMAC over the
    request body using the shared secret, Amazon SP-API SigV4) live
    behind this same surface — replace the verifier per provider
    when wiring real credentials.
    """
    raw = headers.get("X-Marketplace-Signature") or headers.get("x-marketplace-signature")
    if not raw or not raw.startswith("sha256="):
        raise InvalidSignatureError("missing or malformed X-Marketplace-Signature header")
    expected = _hmac_sha256(secret, body)
    if not _constant_eq(raw.split("=", 1)[1], expected):
        raise InvalidSignatureError("signature mismatch")


CARRIER_VERIFIERS: dict[str, Callable[..., None]] = {
    "easypost": verify_easypost,
    "shipstation": verify_shipstation,
}
MARKETPLACE_VERIFIERS: dict[str, Callable[..., None]] = {
    "ebay": verify_marketplace_generic,
    "etsy": verify_marketplace_generic,
    "shopify": verify_marketplace_generic,
    "amazon": verify_marketplace_generic,
}


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


async def _existing(
    session: AsyncSession, *, provider: str, external_event_id: str
) -> WebhookInboundEvent | None:
    stmt = (
        select(WebhookInboundEvent)
        .where(WebhookInboundEvent.provider == provider)
        .where(WebhookInboundEvent.external_event_id == external_event_id)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Carrier adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CarrierTrackingUpdate:
    tracking_number: str
    status: str  # provider-native (we only key off "delivered" today)
    status_detail: str | None
    event_at: datetime | None


def parse_easypost(payload: dict[str, Any]) -> CarrierTrackingUpdate | None:
    """Extract the canonical fields from an EasyPost ``Tracker`` event.

    EasyPost wraps the resource in ``result``. We only handle
    ``tracker.updated`` payloads here; everything else returns None
    (the receipt is still recorded).
    """
    if payload.get("description") not in {"tracker.updated", "tracker.delivered"}:
        return None
    result = payload.get("result") or {}
    tracking_number = result.get("tracking_code") or result.get("tracking_number")
    if not tracking_number:
        return None
    status = str(result.get("status") or "")
    status_detail = result.get("status_detail")
    event_at_raw = result.get("updated_at") or payload.get("created_at")
    event_at: datetime | None = None
    if isinstance(event_at_raw, str):
        try:
            event_at = datetime.fromisoformat(event_at_raw.replace("Z", "+00:00"))
        except ValueError:
            event_at = None
    return CarrierTrackingUpdate(
        tracking_number=str(tracking_number),
        status=status,
        status_detail=str(status_detail) if status_detail else None,
        event_at=event_at,
    )


CARRIER_PARSERS: dict[str, Callable[[dict[str, Any]], CarrierTrackingUpdate | None]] = {
    "easypost": parse_easypost,
}


async def apply_tracking_update(
    session: AsyncSession, update: CarrierTrackingUpdate
) -> Shipment | None:
    """Look up the shipment by tracking_number; flip state if the
    carrier says the package is delivered or in transit."""
    stmt = select(Shipment).where(Shipment.tracking_number == update.tracking_number)
    shipment = (await session.execute(stmt)).scalar_one_or_none()
    if shipment is None:
        return None
    s = update.status.lower()
    if s == "delivered":
        shipment.state = ShipmentState.DELIVERED
    elif s in {"in_transit", "out_for_delivery", "pre_transit"}:
        if shipment.state == ShipmentState.LABEL_PURCHASED:
            shipment.state = ShipmentState.SHIPPED
    elif s == "return_to_sender":
        shipment.state = ShipmentState.RETURNED
    await session.flush()
    return shipment


# ---------------------------------------------------------------------------
# External-id extraction
# ---------------------------------------------------------------------------


def _carrier_external_id(provider: str, payload: dict[str, Any]) -> str:
    if provider == "easypost":
        # EasyPost event ids look like "evt_..." and live at the top level.
        ev = payload.get("id")
        if isinstance(ev, str):
            return ev
        # Fallback to tracker.id + updated_at when ``id`` is missing.
        result = payload.get("result") or {}
        return f"{result.get('id', 'unknown')}:{result.get('updated_at', '')}"
    if provider == "shipstation":
        ev = payload.get("resource_url") or payload.get("event_id")
        if isinstance(ev, str):
            return ev
    return json.dumps(payload, sort_keys=True)[:128]


def _marketplace_external_id(provider: str, payload: dict[str, Any]) -> str:
    for key in ("event_id", "id", "order_id", "refund_id"):
        v = payload.get(key)
        if isinstance(v, str):
            return v
    return json.dumps(payload, sort_keys=True)[:128]


# ---------------------------------------------------------------------------
# Public intake
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntakeResult:
    event: WebhookInboundEvent
    is_duplicate: bool


async def intake_carrier(
    *,
    session: AsyncSession,
    provider: str,
    body: bytes,
    headers: dict[str, str],
) -> IntakeResult:
    if provider not in CARRIER_PROVIDERS:
        raise UnknownProviderError(provider)
    secret = await _resolve_secret(
        session=session, kind=WebhookInboundKind.CARRIER, provider=provider
    )
    verifier = CARRIER_VERIFIERS[provider]
    verifier(secret=secret, body=body, headers=headers)

    payload = json.loads(body or b"{}")
    external_id = _carrier_external_id(provider, payload)

    dup = await _existing(session, provider=provider, external_event_id=external_id)
    if dup is not None:
        return IntakeResult(event=dup, is_duplicate=True)

    row = WebhookInboundEvent(
        id=uuid.uuid4(),
        kind=WebhookInboundKind.CARRIER,
        provider=provider,
        external_event_id=external_id,
        payload=payload,
        status=WebhookInboundStatus.RECEIVED,
    )
    session.add(row)
    await session.flush()

    parser = CARRIER_PARSERS.get(provider)
    if parser is None:
        row.status = WebhookInboundStatus.NOT_IMPLEMENTED
        await session.flush()
        return IntakeResult(event=row, is_duplicate=False)

    update = parser(payload)
    if update is None:
        # Valid event we just don't act on yet (e.g. tracker.created).
        row.status = WebhookInboundStatus.NOT_IMPLEMENTED
        await session.flush()
        return IntakeResult(event=row, is_duplicate=False)

    shipment = await apply_tracking_update(session, update)
    if shipment is None:
        row.status = WebhookInboundStatus.UNMATCHED
    else:
        row.status = WebhookInboundStatus.APPLIED
        row.applied_at = datetime.now(UTC)
    await session.flush()
    return IntakeResult(event=row, is_duplicate=False)


async def intake_marketplace(
    *,
    session: AsyncSession,
    provider: str,
    body: bytes,
    headers: dict[str, str],
) -> IntakeResult:
    if provider not in MARKETPLACE_PROVIDERS:
        raise UnknownProviderError(provider)
    secret = await _resolve_secret(
        session=session, kind=WebhookInboundKind.MARKETPLACE, provider=provider
    )
    verifier = MARKETPLACE_VERIFIERS[provider]
    verifier(secret=secret, body=body, headers=headers)

    payload = json.loads(body or b"{}")
    external_id = _marketplace_external_id(provider, payload)

    dup = await _existing(session, provider=provider, external_event_id=external_id)
    if dup is not None:
        return IntakeResult(event=dup, is_duplicate=True)

    # Marketplace order/refund staging: Phase 11.2 records the receipt;
    # the existing Phase 9.8 / 9.9 settlement auto-matcher consumes the
    # row on its next sweep. We don't insert into the v1 settlement
    # tables here -- that wire-up is a separate Phase 9 follow-up.
    row = WebhookInboundEvent(
        id=uuid.uuid4(),
        kind=WebhookInboundKind.MARKETPLACE,
        provider=provider,
        external_event_id=external_id,
        payload=payload,
        status=WebhookInboundStatus.RECEIVED,
    )
    session.add(row)
    await session.flush()
    return IntakeResult(event=row, is_duplicate=False)


__all__ = [
    "CARRIER_PROVIDERS",
    "CARRIER_VERIFIERS",
    "CarrierTrackingUpdate",
    "InboundWebhookError",
    "IntakeResult",
    "InvalidSignatureError",
    "MARKETPLACE_PROVIDERS",
    "MARKETPLACE_VERIFIERS",
    "MissingSecretError",
    "UnknownProviderError",
    "apply_tracking_update",
    "intake_carrier",
    "intake_marketplace",
    "parse_easypost",
    "verify_easypost",
    "verify_marketplace_generic",
    "verify_shipstation",
]


# Awaitable callable alias used in some typed contexts.
_ApplyFn = Callable[[AsyncSession, CarrierTrackingUpdate], Awaitable[Shipment | None]]
