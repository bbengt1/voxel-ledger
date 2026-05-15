"""Admin endpoint to restart the lazy printer monitor (Phase 5.4).

Owner-only. Idempotent: cancels every running per-printer task, drops
the singleton, then immediately re-instantiates it. Used when an
operator updates a printer's ``moonraker_url`` and wants the monitor
to pick up the change without an app restart.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.models.auth import User
from app.schemas.printer_state import MonitorRestartResponse

router = APIRouter(prefix="/printer-monitor", tags=["admin-printer-monitor"])


@router.post("/restart", response_model=MonitorRestartResponse)
async def restart_printer_monitor(
    _user: Annotated[User, Depends(require_role("owner"))],
) -> MonitorRestartResponse:
    # Lazy import — never load the monitor at module-import time.
    from app.services.printer_monitor import get_monitor, stop_monitor

    await stop_monitor()
    monitor = await get_monitor()
    return MonitorRestartResponse(
        restarted=True,
        printers_monitored=monitor.printers_monitored,
    )
