"""Gcode thumbnail proxy for the printer monitor cards.

Klipper-flavoured slicers embed PNG thumbnails in the gcode and
Moonraker extracts them under ``/server/files/thumbnails/...`` plus
publishes the list via ``/server/files/metadata``. This endpoint:

  1. Reads the printer's Moonraker URL + API key from the catalog.
  2. Picks the current filename from the live printer-state cache.
  3. Asks Moonraker for the file metadata.
  4. Streams back the largest available thumbnail (PNG).

Returns 404 if no print is in progress or the gcode has no embedded
thumbnail; 502 if Moonraker is unreachable. All requests are gated on
``get_current_user`` — same as the live snapshot endpoint.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.services import printers as printers_service

router = APIRouter(prefix="/printers", tags=["printers"])

THUMBNAIL_TIMEOUT_SECONDS: float = 6.0


def _pick_largest_thumbnail(thumbnails: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not thumbnails:
        return None
    sized = [
        t
        for t in thumbnails
        if isinstance(t, dict)
        and isinstance(t.get("width"), int | float)
        and isinstance(t.get("height"), int | float)
        and isinstance(t.get("relative_path"), str)
    ]
    if not sized:
        return None
    sized.sort(
        key=lambda t: float(t["width"]) * float(t["height"]),
        reverse=True,
    )
    return sized[0]


@router.get(
    "/{printer_id}/gcode/thumbnail.png",
    responses={
        200: {"content": {"image/png": {}}},
        404: {"description": "no current print or no embedded thumbnail"},
        502: {"description": "moonraker upstream failed"},
    },
    response_class=Response,
)
async def get_gcode_thumbnail(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        printer = await printers_service.get(session, printer_id)
    except printers_service.PrinterNotFoundError:
        raise HTTPException(status_code=404, detail="printer not found") from None

    if not printer.moonraker_url:
        raise HTTPException(status_code=404, detail="moonraker not configured")

    # Lazy import — the monitor module must not be loaded at boot
    # (Phase 5.4 lazy-load contract).
    from app.services.printer_monitor.monitor import get_monitor

    monitor = await get_monitor()
    state = monitor.get_state(printer_id)
    filename = state.current_file if state else None
    if not filename:
        raise HTTPException(status_code=404, detail="no current file")

    moonraker_base = printer.moonraker_url.rstrip("/")
    headers: dict[str, str] = {}
    if printer.moonraker_api_key:
        headers["X-Api-Key"] = printer.moonraker_api_key

    try:
        async with httpx.AsyncClient(timeout=THUMBNAIL_TIMEOUT_SECONDS) as client:
            meta_resp = await client.get(
                f"{moonraker_base}/server/files/metadata",
                params={"filename": filename},
                headers=headers,
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json().get("result", {}) or {}
            chosen = _pick_largest_thumbnail(meta.get("thumbnails") or [])
            if chosen is None:
                raise HTTPException(
                    status_code=404, detail="no embedded thumbnail"
                ) from None

            # ``relative_path`` is relative to the gcode file's own dir.
            # Compose the absolute URL under ``/server/files/gcodes/``.
            gcode_dir = ""
            if "/" in filename:
                gcode_dir = filename.rsplit("/", 1)[0] + "/"
            thumb_url = (
                f"{moonraker_base}/server/files/gcodes/{gcode_dir}{chosen['relative_path']}"
            )
            thumb_resp = await client.get(thumb_url, headers=headers)
            thumb_resp.raise_for_status()
            body = thumb_resp.content
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — upstream is opaque
        raise HTTPException(
            status_code=502, detail=f"moonraker fetch failed: {exc}"
        ) from None

    return Response(
        content=body,
        media_type="image/png",
        headers={"Cache-Control": "max-age=5, must-revalidate"},
    )
