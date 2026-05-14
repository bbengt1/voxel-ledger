"""Admin audit-log query + CSV export endpoints (Phase 1.4).

Both endpoints share the same filter set and role gate (``owner`` and
``bookkeeper``). The JSON endpoint paginates with an opaque base64 cursor
keyed on ``event_position`` (descending order). The CSV endpoint streams
rows in chunks so a large window doesn't materialize in memory.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.audit import AuditLog
from app.models.auth import User
from app.schemas.audit import AuditLogResponse, AuditLogRow

router = APIRouter(prefix="/audit-log", tags=["admin-audit-log"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
CSV_CHUNK_SIZE = 1000
CSV_COLUMNS: tuple[str, ...] = (
    "event_position",
    "event_id",
    "event_type",
    "occurred_at",
    "actor_user_id",
    "actor_email",
    "actor_role",
    "aggregate_type",
    "aggregate_id",
    "summary",
    "ip_address",
    "payload_excerpt",
)


def _encode_cursor(event_position: int) -> str:
    raw = json.dumps({"p": event_position}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return int(decoded["p"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid cursor"
        ) from exc


def _apply_filters(
    stmt: Select,
    *,
    actor_user_id: uuid.UUID | None,
    event_type: str | None,
    aggregate_type: str | None,
    aggregate_id: uuid.UUID | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
) -> Select:
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if event_type is not None:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if aggregate_type is not None:
        stmt = stmt.where(AuditLog.aggregate_type == aggregate_type)
    if aggregate_id is not None:
        stmt = stmt.where(AuditLog.aggregate_id == aggregate_id)
    if from_ts is not None:
        stmt = stmt.where(AuditLog.occurred_at >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(AuditLog.occurred_at <= to_ts)
    return stmt


@router.get("", response_model=AuditLogResponse)
async def query_audit_log(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    aggregate_type: Annotated[str | None, Query()] = None,
    aggregate_id: Annotated[uuid.UUID | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
) -> AuditLogResponse:
    """Cursor-paginated audit-log query, descending by ``event_position``."""
    stmt = select(AuditLog)
    stmt = _apply_filters(
        stmt,
        actor_user_id=actor_user_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        from_ts=from_,
        to_ts=to,
    )
    if cursor is not None:
        last_position = _decode_cursor(cursor)
        stmt = stmt.where(AuditLog.event_position < last_position)

    stmt = stmt.order_by(AuditLog.event_position.desc()).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    next_cursor = _encode_cursor(rows[-1].event_position) if (rows and has_more) else None
    return AuditLogResponse(
        items=[AuditLogRow.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )


async def _stream_csv_rows(
    session: AsyncSession,
    stmt: Select,
) -> AsyncIterator[str]:
    """Yield CSV chunks. First chunk is the header row; subsequent chunks
    pack up to ``CSV_CHUNK_SIZE`` data rows each.

    We page through the result with a position cursor (descending) instead
    of streaming a single SQLAlchemy result so the connection isn't held
    open for the whole window — a large export should not pin a connection.
    """
    # Header
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    yield buf.getvalue()

    # Data, paged.
    last_position: int | None = None
    while True:
        page_stmt = stmt
        if last_position is not None:
            page_stmt = page_stmt.where(AuditLog.event_position < last_position)
        page_stmt = page_stmt.order_by(AuditLog.event_position.desc()).limit(CSV_CHUNK_SIZE)
        rows = list((await session.execute(page_stmt)).scalars().all())
        if not rows:
            return

        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in rows:
            writer.writerow(
                [
                    row.event_position,
                    str(row.event_id) if row.event_id else "",
                    row.event_type,
                    row.occurred_at.isoformat() if row.occurred_at else "",
                    str(row.actor_user_id) if row.actor_user_id else "",
                    row.actor_email or "",
                    row.actor_role or "",
                    row.aggregate_type,
                    str(row.aggregate_id),
                    row.summary,
                    row.ip_address or "",
                    json.dumps(row.payload_excerpt) if row.payload_excerpt else "",
                ]
            )
        yield buf.getvalue()

        last_position = rows[-1].event_position
        if len(rows) < CSV_CHUNK_SIZE:
            return


@router.get("/export.csv")
async def export_audit_log_csv(
    session: Annotated[AsyncSession, Depends(get_session)],
    _user: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    aggregate_type: Annotated[str | None, Query()] = None,
    aggregate_id: Annotated[uuid.UUID | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
) -> StreamingResponse:
    """Stream the audit log as CSV. Same filters as the JSON endpoint."""
    stmt = select(AuditLog)
    stmt = _apply_filters(
        stmt,
        actor_user_id=actor_user_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        from_ts=from_,
        to_ts=to,
    )
    return StreamingResponse(
        _stream_csv_rows(session, stmt),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'},
    )
