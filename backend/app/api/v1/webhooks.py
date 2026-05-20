"""Outbound webhooks API (Phase 11.1, #193).

Subscription CRUD + delivery history + manual replay. Routers commit
the surrounding transaction; the dispatcher service handles its own
flush/commit semantics. The subscription ``secret`` is returned only
on create and on a rotate-secret PATCH; subsequent reads omit it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.webhook import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)
from app.schemas.webhooks import (
    WebhookDeliveryRead,
    WebhookDeliveryStatusLiteral,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)
from app.services.webhooks import dispatcher

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_ADMIN_ROLES = ("owner", "bookkeeper")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sub_to_read(sub: WebhookSubscription) -> WebhookSubscriptionRead:
    return WebhookSubscriptionRead(
        id=sub.id,
        name=sub.name,
        target_url=sub.target_url,
        event_types=list(sub.event_types or []),
        is_active=sub.is_active,
        created_by_user_id=sub.created_by_user_id,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


def _sub_to_created(sub: WebhookSubscription) -> WebhookSubscriptionCreated:
    return WebhookSubscriptionCreated(
        id=sub.id,
        name=sub.name,
        target_url=sub.target_url,
        event_types=list(sub.event_types or []),
        is_active=sub.is_active,
        created_by_user_id=sub.created_by_user_id,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        secret=sub.secret,
    )


def _delivery_to_read(row: WebhookDelivery) -> WebhookDeliveryRead:
    return WebhookDeliveryRead(
        id=row.id,
        subscription_id=row.subscription_id,
        event_id=row.event_id,
        event_type=row.event_type,
        payload=row.payload or {},
        attempt_count=row.attempt_count,
        last_status=row.last_status.value
        if hasattr(row.last_status, "value")
        else row.last_status,  # type: ignore[arg-type]
        last_response_code=row.last_response_code,
        last_error=row.last_error,
        next_attempt_at=row.next_attempt_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# subscriptions
# ---------------------------------------------------------------------------


@router.post(
    "/subscriptions",
    response_model=WebhookSubscriptionCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    payload: WebhookSubscriptionCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_ADMIN_ROLES))],
) -> WebhookSubscriptionCreated:
    sub = WebhookSubscription(
        id=uuid.uuid4(),
        name=payload.name,
        target_url=str(payload.target_url),
        secret=dispatcher.generate_secret(),
        event_types=list(payload.event_types),
        is_active=payload.is_active,
        created_by_user_id=actor.id,
    )
    session.add(sub)
    await session.flush()
    response = _sub_to_created(sub)
    await session.commit()
    return response


@router.get(
    "/subscriptions",
    response_model=list[WebhookSubscriptionRead],
)
async def list_subscriptions(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_ADMIN_ROLES))],
) -> list[WebhookSubscriptionRead]:
    rows = await dispatcher.list_subscriptions(session)
    return [_sub_to_read(r) for r in rows]


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=WebhookSubscriptionRead,
)
async def get_subscription(
    subscription_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_ADMIN_ROLES))],
) -> WebhookSubscriptionRead:
    try:
        sub = await dispatcher.get_subscription(session, subscription_id)
    except dispatcher.WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="subscription not found") from None
    return _sub_to_read(sub)


@router.patch(
    "/subscriptions/{subscription_id}",
    response_model=WebhookSubscriptionRead | WebhookSubscriptionCreated,
)
async def update_subscription(
    subscription_id: uuid.UUID,
    payload: WebhookSubscriptionUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_ADMIN_ROLES))],
) -> WebhookSubscriptionRead | WebhookSubscriptionCreated:
    try:
        sub = await dispatcher.get_subscription(session, subscription_id)
    except dispatcher.WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="subscription not found") from None

    if payload.name is not None:
        sub.name = payload.name
    if payload.target_url is not None:
        sub.target_url = str(payload.target_url)
    if payload.event_types is not None:
        sub.event_types = list(payload.event_types)
    if payload.is_active is not None:
        sub.is_active = payload.is_active
    rotated = False
    if payload.rotate_secret:
        sub.secret = dispatcher.generate_secret()
        rotated = True
    await session.flush()
    await session.refresh(sub, ["updated_at"])
    response: WebhookSubscriptionRead | WebhookSubscriptionCreated = (
        _sub_to_created(sub) if rotated else _sub_to_read(sub)
    )
    await session.commit()
    return response


@router.delete(
    "/subscriptions/{subscription_id}",
    response_model=WebhookSubscriptionRead,
)
async def delete_subscription(
    subscription_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_ADMIN_ROLES))],
) -> WebhookSubscriptionRead:
    try:
        sub = await dispatcher.get_subscription(session, subscription_id)
    except dispatcher.WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="subscription not found") from None
    sub.is_active = False
    await session.flush()
    await session.refresh(sub, ["updated_at"])
    response = _sub_to_read(sub)
    await session.commit()
    return response


# ---------------------------------------------------------------------------
# deliveries
# ---------------------------------------------------------------------------


@router.get(
    "/deliveries",
    response_model=list[WebhookDeliveryRead],
)
async def list_deliveries(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_ADMIN_ROLES))],
    subscription_id: Annotated[uuid.UUID | None, Query()] = None,
    delivery_status: Annotated[WebhookDeliveryStatusLiteral | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[WebhookDeliveryRead]:
    status_in: list[WebhookDeliveryStatus] | None = None
    if delivery_status is not None:
        status_in = [WebhookDeliveryStatus(delivery_status)]
    rows = await dispatcher.list_deliveries(
        session,
        subscription_id=subscription_id,
        status_in=status_in,
        limit=limit,
    )
    return [_delivery_to_read(r) for r in rows]


@router.post(
    "/deliveries/{delivery_id}/replay",
    response_model=WebhookDeliveryRead,
)
async def replay_delivery(
    delivery_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_ADMIN_ROLES))],
) -> WebhookDeliveryRead:
    try:
        row = await dispatcher.replay(delivery_id, session=session)
    except dispatcher.WebhookNotFoundError:
        raise HTTPException(status_code=404, detail="delivery not found") from None
    response = _delivery_to_read(row)
    await session.commit()
    return response
