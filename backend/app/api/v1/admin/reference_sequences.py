"""Admin endpoint exposing the reference_sequence table (Phase 1.3).

Owner-only read view. The allocator itself runs in-process; this surface
is for operations observability — confirming the table is moving, seeing
which prefixes are live, spotting unexpected year buckets.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.reference_sequence import ReferenceSequence
from app.schemas.reference import ReferenceSequenceRow

router = APIRouter(prefix="/reference-sequences", tags=["admin-reference-sequences"])


@router.get("", response_model=list[ReferenceSequenceRow])
async def list_reference_sequences(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner"))],
) -> list[ReferenceSequenceRow]:
    """Return every ``(prefix, year, last_value)`` row, sorted by
    ``(prefix, year)``."""
    stmt = select(ReferenceSequence).order_by(
        ReferenceSequence.prefix.asc(),
        ReferenceSequence.year.asc(),
    )
    result = await session.execute(stmt)
    return [ReferenceSequenceRow.model_validate(row) for row in result.scalars().all()]
