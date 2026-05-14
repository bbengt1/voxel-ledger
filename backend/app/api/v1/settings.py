"""Operational settings endpoints (Phase 1.5).

- GET /settings              owner + bookkeeper: list with defaults merged.
- GET /settings/{key}        owner + bookkeeper: single setting.
- PUT /settings/{key}        owner: validate + persist + emit event.
- POST /settings:bulk        owner: atomic batch update.

These are NOT mounted under /admin/. Settings reads are part of the
normal business-app flow (cost engine, POS, reference allocator), so the
bookkeeper role can see them too. Writes remain owner-only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.settings import (
    BulkSettingUpdateRequest,
    BulkSettingUpdateResponse,
    SettingResponse,
    SettingUpdateRequest,
)
from app.services.settings.schemas import UnknownSettingError
from app.services.settings.service import (
    SettingRecord,
    SettingsService,
    SettingValidationError,
    _serialize_for_storage,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _record_to_response(rec: SettingRecord) -> SettingResponse:
    """Convert a service-layer record to the API response shape.

    Values are serialized to their JSON-storable form so Decimal returns as
    a canonical string (not a float). The frontend pairs ``schema_type``
    with the raw value to decide how to render it.
    """
    return SettingResponse(
        key=rec.key,
        value=_serialize_for_storage(rec.value),
        default=_serialize_for_storage(rec.default),
        schema_type=rec.schema_type,
        updated_at=rec.updated_at,
        updated_by_user_id=rec.updated_by_user_id,
    )


@router.get("", response_model=list[SettingResponse])
async def list_settings(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> list[SettingResponse]:
    """Return every registered setting, merged with schema defaults."""
    records = await SettingsService.list_all(session=session)
    return [_record_to_response(r) for r in records]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
) -> SettingResponse:
    """Return a single setting by key. 400 on unknown key."""
    try:
        record = await SettingsService.get_record(key, session=session)
    except UnknownSettingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown setting key {key!r}",
        ) from exc
    return _record_to_response(record)


@router.put("/{key}", response_model=SettingResponse)
async def put_setting(
    key: str,
    payload: SettingUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> SettingResponse:
    """Validate and persist a single setting. Emits SettingChanged."""
    try:
        await SettingsService.set(
            key,
            payload.value,
            session=session,
            actor_user_id=user.id,
        )
    except UnknownSettingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown setting key {key!r}",
        ) from exc
    except SettingValidationError as exc:
        # Roll back any partial state the service may have written before
        # the validation error surfaced. The dependency-injected session
        # is owned by FastAPI's request scope; rollback is safe here.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid value for {key!r}: {exc}",
        ) from exc

    await session.commit()
    # Re-read for the response so we return the freshly-persisted row
    # (including the new ``updated_at`` from the DB).
    record = await SettingsService.get_record(key, session=session)
    return _record_to_response(record)


@router.post(":bulk", response_model=BulkSettingUpdateResponse)
async def bulk_update_settings(
    payload: BulkSettingUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(require_role("owner"))],
) -> BulkSettingUpdateResponse:
    """Atomic batch update. One invalid value rolls back everything."""
    try:
        updated = await SettingsService.set_many(
            payload.updates,
            session=session,
            actor_user_id=user.id,
        )
    except UnknownSettingError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except SettingValidationError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await session.commit()
    # Serialize values for the wire (Decimal → canonical string, etc.).
    return BulkSettingUpdateResponse(
        updated={k: _serialize_for_storage(v) for k, v in updated.items()}
    )


__all__ = ["router"]
