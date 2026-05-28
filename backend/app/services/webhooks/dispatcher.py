"""Outbound webhook dispatcher (Phase 11.1, #193).

Flow:

1. The event-store projection :func:`on_event` fires for every
   appended event. For each active ``webhook_subscription`` whose
   ``event_types`` list contains the event's type, one
   ``webhook_delivery`` row lands in state ``pending`` with
   ``next_attempt_at = now``.
2. The every-minute worker (``app/workers/webhook_dispatcher.py``)
   calls :func:`run_pending`. Each pending row whose ``next_attempt_at``
   is in the past is processed by :func:`deliver`.
3. :func:`deliver` signs the JSON body with HMAC-SHA256 using the
   subscription's per-target secret, POSTs with a 10 s timeout, and
   classifies the result:
   - 2xx -> ``delivered``.
   - 4xx (non-429) -> ``failed`` (permanent).
   - 5xx / 429 / timeout / network -> reschedule via
     :func:`backoff_for_attempt`, or flip to ``dead_letter`` once the
     total elapsed time exceeds :data:`MAX_TOTAL_RETRY_SECONDS`.
4. :func:`replay` is the manual retry path used by the
   ``/deliveries/{id}/replay`` endpoint; it resets ``last_status`` to
   ``pending`` and ``next_attempt_at`` to now.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import random
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.webhook import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNATURE_HEADER = "X-Vl-Signature"
DEFAULT_TIMEOUT_SECONDS = 10.0
BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 6 * 3600  # 6 h cap on a single retry delay
MAX_TOTAL_RETRY_SECONDS = 24 * 3600  # 24 h before dead-letter
JITTER_FRACTION = 0.2


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WebhookServiceError(Exception):
    """Base. Routers default to 400."""


class WebhookNotFoundError(WebhookServiceError):
    """Mapped to 404."""


# ---------------------------------------------------------------------------
# Secret generation
# ---------------------------------------------------------------------------


def generate_secret() -> str:
    """Per-target HMAC secret, 32 bytes -> 64 hex chars."""
    return secrets.token_hex(32)


# ---------------------------------------------------------------------------
# Payload + signing
# ---------------------------------------------------------------------------


def _payload_for_event(event: Event) -> dict[str, Any]:
    """The exact dict serialized as the POST body.

    Kept narrow on purpose: subscribers should treat this as a stable
    minimum contract. Avoid leaking ``actor_user_id``/``correlation_id``
    so subscribers cannot cross-reference users.
    """
    return {
        "event_id": str(event.id),
        "type": event.type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id) if event.aggregate_id else None,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": event.payload,
    }


def _canonical_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sign_payload(secret: str, body: bytes) -> str:
    """Return the canonical ``sha256=<hex>`` signature for ``body``."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------


def backoff_for_attempt(
    attempt: int,
    *,
    base: int = BASE_BACKOFF_SECONDS,
    cap: int = MAX_BACKOFF_SECONDS,
    jitter: float = JITTER_FRACTION,
    rng: random.Random | None = None,
) -> int:
    """Return the delay (seconds) before attempt N+1.

    Doubles per attempt, capped at ``cap``, with +-``jitter`` random noise.
    ``attempt`` is the 1-based count of tries already made.
    """
    if attempt < 1:
        attempt = 1
    raw = min(base * (2 ** (attempt - 1)), cap)
    if jitter <= 0:
        return int(raw)
    r = rng or random
    delta = raw * jitter
    return max(1, int(raw + r.uniform(-delta, delta)))


def next_backoff(
    delivery: WebhookDelivery, *, now: datetime, rng: random.Random | None = None
) -> datetime:
    seconds = backoff_for_attempt(delivery.attempt_count, rng=rng)
    return now + timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


async def _active_subscriptions_for_event_type(
    session: AsyncSession, event_type: str
) -> list[WebhookSubscription]:
    rows = (
        (
            await session.execute(
                select(WebhookSubscription).where(WebhookSubscription.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    out: list[WebhookSubscription] = []
    for sub in rows:
        types = sub.event_types or []
        if event_type in types or "*" in types:
            out.append(sub)
    return out


async def enqueue(event: Event, session: AsyncSession) -> list[WebhookDelivery]:
    """Fan-out: one ``webhook_delivery`` per matching subscription.

    Runs inside the same transaction as the originating event append
    (called from a wildcard projection). If no subscription matches,
    this is a no-op.
    """
    subs = await _active_subscriptions_for_event_type(session, event.type)
    if not subs:
        return []

    payload = _payload_for_event(event)
    now = datetime.now(UTC)
    deliveries: list[WebhookDelivery] = []
    for sub in subs:
        row = WebhookDelivery(
            id=uuid.uuid4(),
            subscription_id=sub.id,
            event_id=event.id,
            event_type=event.type,
            payload=payload,
            attempt_count=0,
            last_status=WebhookDeliveryStatus.PENDING,
            next_attempt_at=now,
        )
        session.add(row)
        deliveries.append(row)
    await session.flush()
    return deliveries


# ---------------------------------------------------------------------------
# deliver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliverResult:
    status: WebhookDeliveryStatus
    response_code: int | None
    error: str | None


def _classify(
    *,
    delivery: WebhookDelivery,
    response_code: int | None,
    error: str | None,
    now: datetime,
) -> WebhookDeliveryStatus:
    if response_code is not None and 200 <= response_code < 300:
        return WebhookDeliveryStatus.DELIVERED
    # Permanent failure: 4xx other than 429.
    if response_code is not None and 400 <= response_code < 500 and response_code != 429:
        return WebhookDeliveryStatus.FAILED
    # Retryable: 5xx / 429 / network error / timeout.
    age = (
        now - delivery.created_at.replace(tzinfo=UTC)
        if delivery.created_at.tzinfo is None
        else now - delivery.created_at
    )
    if age.total_seconds() >= MAX_TOTAL_RETRY_SECONDS:
        return WebhookDeliveryStatus.DEAD_LETTER
    return WebhookDeliveryStatus.PENDING


async def deliver(
    delivery_id: uuid.UUID,
    *,
    session: AsyncSession,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> DeliverResult:
    """Deliver one row. Caller commits the surrounding transaction.

    ``client`` is injectable so tests can stub the HTTP roundtrip with
    ``httpx.MockTransport``.
    """
    now = now or datetime.now(UTC)
    row = (
        await session.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id))
    ).scalar_one_or_none()
    if row is None:
        raise WebhookNotFoundError(str(delivery_id))

    sub = (
        await session.execute(
            select(WebhookSubscription).where(WebhookSubscription.id == row.subscription_id)
        )
    ).scalar_one_or_none()
    if sub is None or not sub.is_active:
        row.last_status = WebhookDeliveryStatus.FAILED
        row.last_error = "subscription inactive or missing"
        row.attempt_count += 1
        await session.flush()
        return DeliverResult(
            status=WebhookDeliveryStatus.FAILED,
            response_code=None,
            error=row.last_error,
        )

    body = _canonical_body(row.payload or {})
    signature = sign_payload(sub.secret, body)
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: signature,
        "X-Vl-Event-Type": row.event_type,
        "X-Vl-Delivery-Id": str(row.id),
    }

    response_code: int | None = None
    error: str | None = None

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
    try:
        try:
            resp = await http_client.post(sub.target_url, content=body, headers=headers)
            response_code = resp.status_code
            if response_code >= 400:
                # Capture a short snippet for the operator. Never trust
                # remote content as PII-free; keep it short and never
                # whitelist ``last_error`` into audit excerpts.
                error = (resp.text or "")[:512] or None
        except httpx.TimeoutException as exc:
            error = f"timeout: {exc.__class__.__name__}"
        except httpx.HTTPError as exc:
            error = f"http_error: {exc.__class__.__name__}: {exc}"[:512]
    finally:
        if owns_client:
            await http_client.aclose()

    row.attempt_count += 1
    row.last_response_code = response_code
    row.last_error = error
    new_status = _classify(delivery=row, response_code=response_code, error=error, now=now)
    row.last_status = new_status
    if new_status == WebhookDeliveryStatus.PENDING:
        row.next_attempt_at = next_backoff(row, now=now, rng=rng)
    await session.flush()
    return DeliverResult(status=new_status, response_code=response_code, error=error)


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


async def replay(delivery_id: uuid.UUID, *, session: AsyncSession) -> WebhookDelivery:
    row = (
        await session.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id))
    ).scalar_one_or_none()
    if row is None:
        raise WebhookNotFoundError(str(delivery_id))
    row.last_status = WebhookDeliveryStatus.PENDING
    row.next_attempt_at = datetime.now(UTC)
    row.last_error = None
    await session.flush()
    await session.refresh(row, ["updated_at"])
    return row


# ---------------------------------------------------------------------------
# run_pending (worker entrypoint)
# ---------------------------------------------------------------------------


async def _pending_due(session: AsyncSession, *, now: datetime, limit: int) -> list[uuid.UUID]:
    stmt = (
        select(WebhookDelivery.id)
        .where(WebhookDelivery.last_status == WebhookDeliveryStatus.PENDING)
        .where(WebhookDelivery.next_attempt_at <= now)
        .order_by(WebhookDelivery.next_attempt_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@dataclass(frozen=True)
class RunPendingResult:
    delivered: int
    retried: int
    failed: int
    dead_lettered: int


async def run_pending(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    max_per_run: int = 50,
    client: httpx.AsyncClient | None = None,
    rng: random.Random | None = None,
) -> RunPendingResult:
    """Drain up to ``max_per_run`` due deliveries.

    Each delivery is processed and committed independently so one
    failure doesn't block the rest.
    """
    now = now or datetime.now(UTC)
    ids = await _pending_due(session, now=now, limit=max_per_run)

    delivered = retried = failed = dead = 0

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS)
    try:
        for delivery_id in ids:
            try:
                result = await deliver(
                    delivery_id,
                    session=session,
                    client=http_client,
                    now=now,
                    rng=rng,
                )
                await session.commit()
            except Exception as exc:  # pragma: no cover - defensive
                log.exception(
                    "webhook_dispatcher.deliver_failed",
                    extra={"delivery_id": str(delivery_id)},
                )
                await session.rollback()
                _ = exc
                failed += 1
                continue
            if result.status == WebhookDeliveryStatus.DELIVERED:
                delivered += 1
            elif result.status == WebhookDeliveryStatus.PENDING:
                retried += 1
            elif result.status == WebhookDeliveryStatus.DEAD_LETTER:
                dead += 1
            else:
                failed += 1
    finally:
        if owns_client:
            await http_client.aclose()
    return RunPendingResult(delivered=delivered, retried=retried, failed=failed, dead_lettered=dead)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def list_subscriptions(session: AsyncSession) -> list[WebhookSubscription]:
    return list(
        (
            await session.execute(
                select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def get_subscription(
    session: AsyncSession, subscription_id: uuid.UUID
) -> WebhookSubscription:
    row = (
        await session.execute(
            select(WebhookSubscription).where(WebhookSubscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise WebhookNotFoundError(str(subscription_id))
    return row


async def list_deliveries(
    session: AsyncSession,
    *,
    subscription_id: uuid.UUID | None = None,
    status_in: Iterable[WebhookDeliveryStatus] | None = None,
    limit: int = 100,
) -> list[WebhookDelivery]:
    stmt = select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(limit)
    if subscription_id is not None:
        stmt = stmt.where(WebhookDelivery.subscription_id == subscription_id)
    if status_in is not None:
        stmt = stmt.where(WebhookDelivery.last_status.in_(list(status_in)))
    return list((await session.execute(stmt)).scalars().all())


async def get_delivery(session: AsyncSession, delivery_id: uuid.UUID) -> WebhookDelivery:
    row = (
        await session.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id))
    ).scalar_one_or_none()
    if row is None:
        raise WebhookNotFoundError(str(delivery_id))
    return row


__all__ = [
    "BASE_BACKOFF_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DeliverResult",
    "JITTER_FRACTION",
    "MAX_BACKOFF_SECONDS",
    "MAX_TOTAL_RETRY_SECONDS",
    "RunPendingResult",
    "SIGNATURE_HEADER",
    "WebhookNotFoundError",
    "WebhookServiceError",
    "backoff_for_attempt",
    "deliver",
    "enqueue",
    "generate_secret",
    "get_delivery",
    "get_subscription",
    "list_deliveries",
    "list_subscriptions",
    "next_backoff",
    "replay",
    "run_pending",
    "sign_payload",
]
