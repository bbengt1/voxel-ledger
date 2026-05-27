"""Global search endpoint (#251).

``GET /api/v1/search?q=<query>`` — returns a flat list of hits across
every searchable entity in the app. Operators hit this from the
top-bar omnibar to jump to any row by name or number.

Open to every authenticated role — search is read-only and only
surfaces rows the operator could already reach by clicking through.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.services import search as search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def global_search(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=0, max_length=128)] = "",
) -> dict[str, list[dict[str, Any]]]:
    items = await search_service.search(session, q)
    return {"items": items}
