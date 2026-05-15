"""Sales channels API (Phase 6.1, #93).

Thin layer over ``app.services.sales_channels``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role. Owner + bookkeeper write; owner + bookkeeper + sales read.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.sales_channel import SalesChannel
from app.schemas.sales_channels import (
    SalesChannelCreate,
    SalesChannelListResponse,
    SalesChannelResponse,
    SalesChannelUpdate,
)
from app.services import sales_channels as channels_service

router = APIRouter(prefix="/sales-channels", tags=["sales-channels"])


def _to_response(channel: SalesChannel) -> SalesChannelResponse:
    return SalesChannelResponse(
        id=channel.id,
        name=channel.name,
        slug=channel.slug,
        kind=channel.kind.value,  # type: ignore[arg-type]
        fee_model=channel.fee_model.value,  # type: ignore[arg-type]
        fee_percent=channel.fee_percent,
        fee_flat=channel.fee_flat,
        is_active=channel.is_active,
        default_revenue_account_id=channel.default_revenue_account_id,
        default_fee_account_id=channel.default_fee_account_id,
        external_id_format_hint=channel.external_id_format_hint,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, channels_service.SalesChannelNotFoundError):
        return HTTPException(status_code=404, detail="sales channel not found")
    if isinstance(exc, channels_service.DuplicateSalesChannelError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, channels_service.InvalidFeeConfigurationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, channels_service.SalesChannelsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.post("", response_model=SalesChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_sales_channel(
    payload: SalesChannelCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> SalesChannelResponse:
    try:
        channel = await channels_service.create(
            session,
            name=payload.name,
            slug=payload.slug,
            kind=payload.kind,
            fee_model=payload.fee_model,
            fee_percent=payload.fee_percent,
            fee_flat=payload.fee_flat,
            default_revenue_account_id=payload.default_revenue_account_id,
            default_fee_account_id=payload.default_fee_account_id,
            external_id_format_hint=payload.external_id_format_hint,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(channel, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(channel)


@router.get("", response_model=SalesChannelListResponse)
async def list_sales_channels(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
    active: Annotated[bool | None, Query()] = None,
) -> SalesChannelListResponse:
    rows = await channels_service.list_channels(session, active=active)
    return SalesChannelListResponse(items=[_to_response(c) for c in rows])


@router.get("/{channel_id}", response_model=SalesChannelResponse)
async def get_sales_channel(
    channel_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "bookkeeper", "sales"))],
) -> SalesChannelResponse:
    try:
        channel = await channels_service.get(session, channel_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(channel)


@router.patch("/{channel_id}", response_model=SalesChannelResponse)
async def update_sales_channel(
    channel_id: uuid.UUID,
    payload: SalesChannelUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> SalesChannelResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        channel = await channels_service.update(
            session, channel_id=channel_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(channel, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(channel)


@router.post("/{channel_id}/archive", response_model=SalesChannelResponse)
async def archive_sales_channel(
    channel_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> SalesChannelResponse:
    try:
        channel = await channels_service.archive(
            session, channel_id=channel_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(channel, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(channel)


@router.post("/{channel_id}/unarchive", response_model=SalesChannelResponse)
async def unarchive_sales_channel(
    channel_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> SalesChannelResponse:
    try:
        channel = await channels_service.unarchive(
            session, channel_id=channel_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.refresh(channel, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(channel)
