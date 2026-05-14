"""Admin event-log endpoints.

Currently exposes only ``verify-chain``. Future surfaces (replay
control, projection rebuilds) will hang off the same router.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.events import VerifyChainResponse
from app.services import event_store

router = APIRouter(prefix="/events", tags=["admin-events"])

MAX_VERIFY_WINDOW = 1_000_000


@router.get("/verify-chain", response_model=VerifyChainResponse)
async def verify_chain(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
    from_position: int = Query(default=0, ge=0),
    to_position: int | None = Query(default=None, ge=1),
) -> VerifyChainResponse:
    """Walk the event log in ``position`` order and recompute every hash.

    Window-bounded: ``to_position - from_position`` may not exceed 1M.
    Returns ``ok=true`` for a clean chain, otherwise ``ok=false`` with
    the position where the chain first breaks.
    """
    if to_position is not None:
        if to_position < from_position:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="to_position must be >= from_position",
            )
        if (to_position - from_position) > MAX_VERIFY_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"window exceeds {MAX_VERIFY_WINDOW} rows; narrow the range",
            )

    result = await event_store.verify_chain(
        session,
        from_position=from_position,
        to_position=to_position,
    )
    return VerifyChainResponse(
        ok=result.ok,
        last_position=result.last_position,
        broken_at_position=result.broken_at_position,
        events_checked=result.events_checked,
    )
