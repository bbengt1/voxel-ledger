"""Health endpoint.

Returns 200 only when the configured database accepts a `SELECT 1`. Anything
else surfaces as 503 so an upstream load balancer can route around the node.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.db import get_session
from app.core.logging import get_logger

router = APIRouter(tags=["platform"])
log = get_logger(__name__)


@router.get("/health")
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    """Liveness + DB reachability probe."""
    try:
        result = await session.execute(text("SELECT 1"))
        result.scalar_one()
    except Exception as exc:
        log.warning("health.db_unreachable", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unreachable",
        ) from exc

    return {"status": "ok", "version": __version__}
