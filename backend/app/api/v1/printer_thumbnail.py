"""Moonraker gcode proxy endpoints for a printer.

Three thin proxies, all gated on ``get_current_user``:

  - ``GET /printers/{id}/gcode/thumbnail.png[?filename=…]`` — picks the
    largest embedded PNG thumbnail and returns it. Defaults to the
    currently-printing file when ``filename`` is omitted.
  - ``GET /printers/{id}/gcode-files`` — flat list of gcode files on
    the printer (Moonraker's ``/server/files/list?root=gcodes``).
  - ``GET /printers/{id}/gcode/metadata?filename=…`` — passthrough of
    Moonraker's metadata for one file (used by the file-browser modal
    to derive thumbnail URLs without a second round-trip).

Returns 404 when no print is in progress or no thumbnail exists; 502
when Moonraker is unreachable.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.auth import User
from app.models.printer import Printer
from app.services import printers as printers_service

router = APIRouter(prefix="/printers", tags=["printers"])

MOONRAKER_TIMEOUT_SECONDS: float = 8.0


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


async def _load_printer_or_404(
    session: AsyncSession, printer_id: uuid.UUID
) -> Printer:
    try:
        printer = await printers_service.get(session, printer_id)
    except printers_service.PrinterNotFoundError:
        raise HTTPException(status_code=404, detail="printer not found") from None
    if not printer.moonraker_url:
        raise HTTPException(status_code=404, detail="moonraker not configured")
    return printer


def _auth_headers(printer: Printer) -> dict[str, str]:
    return {"X-Api-Key": printer.moonraker_api_key} if printer.moonraker_api_key else {}


# ---------------------------------------------------------------------------
# Thumbnail
# ---------------------------------------------------------------------------


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
    filename: Annotated[str | None, Query()] = None,
) -> Response:
    printer = await _load_printer_or_404(session, printer_id)

    target_filename = filename
    if target_filename is None:
        # Lazy import — the monitor module must not load at boot.
        from app.services.printer_monitor.monitor import get_monitor

        monitor = await get_monitor()
        state = monitor.get_state(printer_id)
        target_filename = state.current_file if state else None

    if not target_filename:
        raise HTTPException(status_code=404, detail="no current file")

    moonraker_base = printer.moonraker_url.rstrip("/")  # type: ignore[union-attr]
    headers = _auth_headers(printer)

    try:
        async with httpx.AsyncClient(timeout=MOONRAKER_TIMEOUT_SECONDS) as client:
            meta_resp = await client.get(
                f"{moonraker_base}/server/files/metadata",
                params={"filename": target_filename},
                headers=headers,
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json().get("result", {}) or {}
            chosen = _pick_largest_thumbnail(meta.get("thumbnails") or [])
            if chosen is None:
                raise HTTPException(status_code=404, detail="no embedded thumbnail")

            gcode_dir = ""
            if "/" in target_filename:
                gcode_dir = target_filename.rsplit("/", 1)[0] + "/"
            thumb_url = (
                f"{moonraker_base}/server/files/gcodes/"
                f"{gcode_dir}{chosen['relative_path']}"
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
        headers={"Cache-Control": "max-age=30, must-revalidate"},
    )


# ---------------------------------------------------------------------------
# File list
# ---------------------------------------------------------------------------


@router.get("/{printer_id}/gcode-files")
async def list_gcode_files(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """List gcode files on the printer (flat, all subfolders included)."""
    printer = await _load_printer_or_404(session, printer_id)
    moonraker_base = printer.moonraker_url.rstrip("/")  # type: ignore[union-attr]

    try:
        async with httpx.AsyncClient(timeout=MOONRAKER_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{moonraker_base}/server/files/list",
                params={"root": "gcodes"},
                headers=_auth_headers(printer),
            )
            resp.raise_for_status()
            payload = resp.json().get("result") or []
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"moonraker fetch failed: {exc}"
        ) from None

    items = [
        {
            "path": entry.get("path") or entry.get("filename"),
            "size": entry.get("size"),
            "modified": entry.get("modified"),
        }
        for entry in payload
        if isinstance(entry, dict)
        and (entry.get("path") or entry.get("filename"))
    ]
    # Newest first; Moonraker returns modified as a unix timestamp.
    items.sort(key=lambda r: r.get("modified") or 0, reverse=True)
    return {"items": items}


# ---------------------------------------------------------------------------
# Metadata (for the file browser modal — derives the per-file fields it
# wants to show without a second round-trip per file).
# ---------------------------------------------------------------------------


@router.get("/{printer_id}/gcode/metadata")
async def get_gcode_metadata(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    filename: Annotated[str, Query(min_length=1)],
) -> dict[str, Any]:
    """Return the raw Moonraker metadata for one gcode file."""
    printer = await _load_printer_or_404(session, printer_id)
    moonraker_base = printer.moonraker_url.rstrip("/")  # type: ignore[union-attr]

    try:
        async with httpx.AsyncClient(timeout=MOONRAKER_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{moonraker_base}/server/files/metadata",
                params={"filename": filename},
                headers=_auth_headers(printer),
            )
            resp.raise_for_status()
            data = resp.json().get("result") or {}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"moonraker fetch failed: {exc}"
        ) from None
    return data
