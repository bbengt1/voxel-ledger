"""Per-user preferences endpoints (#258).

``GET/PUT /api/v1/me/preferences/{key}`` — a small key/value store scoped
to the authenticated user, used for UI preferences that should follow the
user across sessions/devices (e.g. per-table column visibility). The value
is opaque JSON; the client owns its shape per key.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.models.user_preference import UserPreference

router = APIRouter(prefix="/me/preferences", tags=["preferences"])


class PreferenceValue(BaseModel):
    """A JSON object value. Constrained to a dict so keys stay structured
    (e.g. ``{"visible": ["sku", "name"]}``)."""

    value: dict[str, Any]


class PreferenceResponse(BaseModel):
    key: str
    value: dict[str, Any]


@router.get("/{key}", response_model=PreferenceResponse)
async def get_preference(
    key: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> PreferenceResponse:
    row = (
        await session.execute(
            select(UserPreference).where(
                UserPreference.user_id == user.id,
                UserPreference.key == key,
            )
        )
    ).scalar_one_or_none()
    # Unset preferences return an empty object rather than 404 so the
    # client can treat "no preference yet" as "use defaults" without
    # branching on status codes.
    if row is None:
        return PreferenceResponse(key=key, value={})
    return PreferenceResponse(key=key, value=dict(row.value or {}))


@router.put("/{key}", response_model=PreferenceResponse, status_code=status.HTTP_200_OK)
async def put_preference(
    key: str,
    payload: PreferenceValue,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> PreferenceResponse:
    row = (
        await session.execute(
            select(UserPreference).where(
                UserPreference.user_id == user.id,
                UserPreference.key == key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserPreference(user_id=user.id, key=key, value=payload.value)
        session.add(row)
    else:
        row.value = payload.value
    await session.commit()
    return PreferenceResponse(key=key, value=payload.value)
