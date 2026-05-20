"""Outbound webhook dispatcher tests (Phase 11.1, #193)."""

from __future__ import annotations

import json
import random
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from app.events.types._test_event import TYPE as TEST_EVENT_TYPE
from app.models.webhook import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.webhooks import dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_sub(
    session: AsyncSession,
    *,
    event_types: list[str] | None = None,
    is_active: bool = True,
    secret: str | None = None,
) -> WebhookSubscription:
    sub = WebhookSubscription(
        id=uuid.uuid4(),
        name="hookA",
        target_url="https://example.test/hook",
        secret=secret or dispatcher.generate_secret(),
        event_types=event_types if event_types is not None else [TEST_EVENT_TYPE],
        is_active=is_active,
    )
    session.add(sub)
    await session.flush()
    return sub


async def _append_test_event(session: AsyncSession) -> uuid.UUID:
    ev = await event_store.append(
        EventCreate(
            type=TEST_EVENT_TYPE,
            aggregate_type="test",
            aggregate_id=uuid.uuid4(),
            payload={"value": "hi"},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
        ),
        session=session,
    )
    return ev.id


def _client_returning(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5.0)


# ---------------------------------------------------------------------------
# signing
# ---------------------------------------------------------------------------


def test_sign_payload_matches_recompute() -> None:
    body = json.dumps({"a": 1, "b": [1, 2, 3]}, sort_keys=True).encode("utf-8")
    sig = dispatcher.sign_payload("s3cret", body)
    assert sig.startswith("sha256=")
    # Recomputing yields the same value.
    assert sig == dispatcher.sign_payload("s3cret", body)
    # Different secret -> different signature.
    assert sig != dispatcher.sign_payload("other", body)


# ---------------------------------------------------------------------------
# enqueue (via projection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_fans_out_to_matching_active_subscriptions(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session, event_types=[TEST_EVENT_TYPE])
    await _make_sub(app_session, event_types=["other.event"])
    inactive = await _make_sub(app_session, event_types=[TEST_EVENT_TYPE])
    inactive.is_active = False
    await app_session.commit()

    await _append_test_event(app_session)
    await app_session.commit()

    rows = (await app_session.execute(select(WebhookDelivery))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == TEST_EVENT_TYPE
    assert rows[0].last_status == WebhookDeliveryStatus.PENDING


@pytest.mark.asyncio
async def test_wildcard_subscription_matches_any_event(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session, event_types=["*"])
    await app_session.commit()

    await _append_test_event(app_session)
    await app_session.commit()

    rows = (await app_session.execute(select(WebhookDelivery))).scalars().all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# deliver: classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_2xx_marks_delivered_and_signs_payload(
    client, app_session: AsyncSession
) -> None:
    sub = await _make_sub(app_session, secret="k" * 64)
    await app_session.commit()
    await _append_test_event(app_session)
    await app_session.commit()
    delivery = (await app_session.execute(select(WebhookDelivery))).scalars().one()

    received: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received["sig"] = request.headers.get(dispatcher.SIGNATURE_HEADER)
        received["body"] = request.content
        received["type_header"] = request.headers.get("X-Vl-Event-Type")
        return httpx.Response(200, json={"ok": True})

    async with _client_returning(handler) as http:
        result = await dispatcher.deliver(delivery.id, session=app_session, client=http)
    assert result.status == WebhookDeliveryStatus.DELIVERED
    assert received["type_header"] == TEST_EVENT_TYPE
    # Signature verifies against the body.
    expected = dispatcher.sign_payload(sub.secret, received["body"])  # type: ignore[arg-type]
    assert received["sig"] == expected


@pytest.mark.asyncio
async def test_deliver_5xx_reschedules_with_backoff(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session)
    await app_session.commit()
    await _append_test_event(app_session)
    await app_session.commit()
    delivery = (await app_session.execute(select(WebhookDelivery))).scalars().one()
    before = delivery.next_attempt_at

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")

    now = datetime.now(UTC)
    rng = random.Random(0)
    async with _client_returning(handler) as http:
        result = await dispatcher.deliver(
            delivery.id, session=app_session, client=http, now=now, rng=rng
        )
    assert result.status == WebhookDeliveryStatus.PENDING
    refreshed = (
        await app_session.execute(select(WebhookDelivery).where(WebhookDelivery.id == delivery.id))
    ).scalar_one()
    assert refreshed.attempt_count == 1
    assert refreshed.last_response_code == 503
    # next_attempt_at is in the future, roughly base * 2^0 = 30s +/- jitter.
    delta = (refreshed.next_attempt_at - now).total_seconds()
    assert 24 <= delta <= 36
    # And different from the original.
    assert refreshed.next_attempt_at != before


@pytest.mark.asyncio
async def test_deliver_4xx_marks_failed_no_retry(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session)
    await app_session.commit()
    await _append_test_event(app_session)
    await app_session.commit()
    delivery = (await app_session.execute(select(WebhookDelivery))).scalars().one()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="nope")

    async with _client_returning(handler) as http:
        result = await dispatcher.deliver(delivery.id, session=app_session, client=http)
    assert result.status == WebhookDeliveryStatus.FAILED


@pytest.mark.asyncio
async def test_deliver_429_is_retryable(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session)
    await app_session.commit()
    await _append_test_event(app_session)
    await app_session.commit()
    delivery = (await app_session.execute(select(WebhookDelivery))).scalars().one()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    async with _client_returning(handler) as http:
        result = await dispatcher.deliver(
            delivery.id, session=app_session, client=http, rng=random.Random(0)
        )
    assert result.status == WebhookDeliveryStatus.PENDING


@pytest.mark.asyncio
async def test_deliver_dead_letters_after_24h(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session)
    await app_session.commit()
    await _append_test_event(app_session)
    await app_session.commit()
    delivery = (await app_session.execute(select(WebhookDelivery))).scalars().one()
    # Backdate the created_at past the 24h cutoff.
    delivery.created_at = datetime.now(UTC) - timedelta(hours=25)
    await app_session.commit()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with _client_returning(handler) as http:
        result = await dispatcher.deliver(delivery.id, session=app_session, client=http)
    assert result.status == WebhookDeliveryStatus.DEAD_LETTER


# ---------------------------------------------------------------------------
# backoff math
# ---------------------------------------------------------------------------


def test_backoff_doubles_and_caps() -> None:
    def no_jitter(n: int) -> int:
        return dispatcher.backoff_for_attempt(n, jitter=0.0)

    assert no_jitter(1) == 30
    assert no_jitter(2) == 60
    assert no_jitter(3) == 120
    # Cap at MAX_BACKOFF_SECONDS = 6h.
    assert no_jitter(20) == dispatcher.MAX_BACKOFF_SECONDS


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_resets_to_pending_and_now(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session)
    await app_session.commit()
    await _append_test_event(app_session)
    await app_session.commit()
    delivery = (await app_session.execute(select(WebhookDelivery))).scalars().one()
    delivery.last_status = WebhookDeliveryStatus.FAILED
    delivery.last_error = "old"
    delivery.next_attempt_at = datetime.now(UTC) + timedelta(hours=2)
    await app_session.commit()

    row = await dispatcher.replay(delivery.id, session=app_session)
    assert row.last_status == WebhookDeliveryStatus.PENDING
    assert row.last_error is None
    assert row.next_attempt_at <= datetime.now(UTC) + timedelta(seconds=2)


# ---------------------------------------------------------------------------
# run_pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pending_processes_due_only(
    client, app_session: AsyncSession
) -> None:
    await _make_sub(app_session)
    await app_session.commit()

    # Two events -> two deliveries.
    await _append_test_event(app_session)
    await _append_test_event(app_session)
    await app_session.commit()

    deliveries = (
        await app_session.execute(select(WebhookDelivery).order_by(WebhookDelivery.created_at))
    ).scalars().all()
    assert len(deliveries) == 2
    # Push one delivery into the future.
    deliveries[1].next_attempt_at = datetime.now(UTC) + timedelta(hours=1)
    await app_session.commit()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async with _client_returning(handler) as http:
        result = await dispatcher.run_pending(
            session=app_session, client=http, max_per_run=10
        )
    assert result.delivered == 1
    assert result.retried == 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def _seed_owner_via_api(client, app_session: AsyncSession, *, email: str) -> str:
    from app.models.auth import Role
    from app.services.auth import create_user

    await create_user(
        app_session,
        email=email,
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pw-correct"}
    )
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_endpoints_create_get_replay(client, app_session: AsyncSession) -> None:
    token = await _seed_owner_via_api(client, app_session, email="wh@example.com")
    hdrs = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v1/webhooks/subscriptions",
        headers=hdrs,
        json={
            "name": "hookA",
            "target_url": "https://example.test/hook",
            "event_types": [TEST_EVENT_TYPE],
            "is_active": True,
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    sub_id = body["id"]
    assert body["secret"]  # secret returned once on create
    secret_one = body["secret"]

    # GET hides the secret.
    got = await client.get(f"/api/v1/webhooks/subscriptions/{sub_id}", headers=hdrs)
    assert got.status_code == 200
    assert "secret" not in got.json()

    # PATCH with rotate_secret=true returns a new secret.
    rot = await client.patch(
        f"/api/v1/webhooks/subscriptions/{sub_id}",
        headers=hdrs,
        json={"rotate_secret": True},
    )
    assert rot.status_code == 200
    assert rot.json()["secret"] != secret_one

    # PATCH without rotate doesn't return one.
    edit = await client.patch(
        f"/api/v1/webhooks/subscriptions/{sub_id}",
        headers=hdrs,
        json={"name": "renamed"},
    )
    assert edit.status_code == 200
    assert "secret" not in edit.json()

    # Trigger a delivery via the projection.
    await _append_test_event(app_session)
    await app_session.commit()

    deliveries = await client.get(
        "/api/v1/webhooks/deliveries",
        headers=hdrs,
        params={"subscription_id": sub_id},
    )
    assert deliveries.status_code == 200
    assert len(deliveries.json()) == 1
    delivery_id = deliveries.json()[0]["id"]

    # Replay round-trip.
    replay = await client.post(
        f"/api/v1/webhooks/deliveries/{delivery_id}/replay", headers=hdrs
    )
    assert replay.status_code == 200
    assert replay.json()["last_status"] == "pending"
