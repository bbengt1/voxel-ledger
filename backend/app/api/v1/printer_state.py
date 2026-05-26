"""Printer live-state + history endpoints (Phase 5.4).

These endpoints are the first touchpoint that imports
``app.services.printer_monitor`` (a lazy-loaded module — see its
docstring). Calling ``/state`` is what kicks the singleton off; until
the first probe completes the response is ``503 monitor_warming_up``
with ``Retry-After: 5``.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.models.printer import Printer
from app.models.printer_history_event import PrinterHistoryEvent
from app.schemas.printer_state import (
    PrinterHistoryEventResponse,
    PrinterHistoryListResponse,
    PrinterStateResponse,
    PrinterTemperatures,
)

router = APIRouter(prefix="/printers", tags=["printers-state"])


def _encode_history_cursor(occurred_at: datetime, event_id: uuid.UUID) -> str:
    raw = json.dumps({"o": occurred_at.isoformat(), "i": str(event_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_history_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["o"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid cursor: {exc}") from None


@router.get("/{printer_id}/state", response_model=PrinterStateResponse)
async def get_printer_state(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> PrinterStateResponse:
    # Verify the printer exists. 404 short-circuits before we kick the
    # monitor — no point spinning up tasks for a bogus id.
    stmt = select(Printer).where(Printer.id == printer_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="printer not found")

    # LAZY-LOAD here. This is the only path that imports the monitor in
    # the normal request lifecycle.
    from app.services.printer_monitor import get_monitor

    monitor = await get_monitor()
    state = monitor.get_state(printer_id)

    if state is None:
        # Printer exists but has no moonraker_url, so it's not monitored.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monitor_warming_up",
            headers={"Retry-After": "5"},
        )

    if state.last_seen_at is None and state.state == "disconnected":
        # First tick hasn't completed yet (or first tick failed). Tell
        # the client to retry rather than returning a stale-by-default
        # snapshot.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monitor_warming_up",
            headers={"Retry-After": "5"},
        )

    return PrinterStateResponse(
        printer_id=state.printer_id,
        state=state.state,  # type: ignore[arg-type]
        progress_pct=state.progress_pct,
        elapsed_seconds=state.elapsed_seconds,
        remaining_seconds_estimate=state.remaining_seconds_estimate,
        current_file=state.current_file,
        temperatures=PrinterTemperatures(
            extruder=state.temperatures.get("extruder"),
            bed=state.temperatures.get("bed"),
        ),
        speed_mm_s=state.speed_mm_s,
        flow_mm3_s=state.flow_mm3_s,
        filament_used_mm=state.filament_used_mm,
        current_layer=state.current_layer,
        total_layers=state.total_layers,
        last_seen_at=state.last_seen_at,
    )


@router.get("/{printer_id}/history", response_model=PrinterHistoryListResponse)
async def list_printer_history(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    from_at: Annotated[datetime | None, Query()] = None,
    to_at: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PrinterHistoryListResponse:
    exists = (
        await session.execute(select(Printer.id).where(Printer.id == printer_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="printer not found")

    stmt = select(PrinterHistoryEvent).where(PrinterHistoryEvent.printer_id == printer_id)
    if from_at is not None:
        stmt = stmt.where(PrinterHistoryEvent.occurred_at >= from_at)
    if to_at is not None:
        stmt = stmt.where(PrinterHistoryEvent.occurred_at <= to_at)
    if cursor is not None:
        anchor_at, anchor_id = _decode_history_cursor(cursor)
        # Descending paging: next page = strictly older than the anchor.
        stmt = stmt.where(
            (PrinterHistoryEvent.occurred_at < anchor_at)
            | (
                (PrinterHistoryEvent.occurred_at == anchor_at)
                & (PrinterHistoryEvent.id < anchor_id)
            )
        )

    stmt = stmt.order_by(
        PrinterHistoryEvent.occurred_at.desc(),
        PrinterHistoryEvent.id.desc(),
    ).limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    next_cursor: str | None = None
    if rows and has_more:
        last = rows[-1]
        next_cursor = _encode_history_cursor(last.occurred_at, last.id)

    return PrinterHistoryListResponse(
        items=[
            PrinterHistoryEventResponse(
                id=row.id,
                printer_id=row.printer_id,
                event_kind=row.event_kind.value,  # type: ignore[arg-type]
                occurred_at=row.occurred_at,
                details=row.details,
            )
            for row in rows
        ],
        next_cursor=next_cursor,
    )
