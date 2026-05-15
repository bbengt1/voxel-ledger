"""Cameras service (Phase 5.1).

CRUD for the ``camera`` aggregate. A camera is 1:1 with a printer; the
DB enforces ``UNIQUE(printer_id)``. The service treats ``POST .../cameras``
as an idempotent upsert — set-or-replace — so callers don't have to
worry about whether a config already exists.

The snapshot proxy lives in this module too. For v1, only ``go2rtc`` is
end-to-end supported (HTTP basic auth + JPEG body). Other kinds are
accepted by the table but the snapshot endpoint returns 501 for them.

**Secret handling.** ``password_secret`` is opaque. The update-event
diff substitutes ``"***"`` for both before and after. The configured
event omits the field entirely. Regression-tested.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import production as production_events
from app.models.camera import Camera, CameraKind
from app.models.printer import Printer
from app.schemas.events import EventCreate
from app.services import event_store

SECRET_SENTINEL = "***"
SNAPSHOT_CACHE_TTL_SECONDS = 2.0


class CamerasServiceError(Exception):
    """Base class. Routers map to 400."""


class CameraNotFoundError(CamerasServiceError):
    pass


class PrinterNotFoundForCameraError(CamerasServiceError):
    pass


class UnsupportedCameraKindError(CamerasServiceError):
    """Raised when the snapshot proxy is asked for a kind it doesn't
    know how to fetch in v1. The router maps this to 501."""


class CameraUpstreamError(CamerasServiceError):
    """Raised when the upstream snapshot fetch fails. Router → 502."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=production_events.AGGREGATE_TYPE_CAMERA,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _coerce_kind(kind: str | CameraKind) -> CameraKind:
    if isinstance(kind, CameraKind):
        return kind
    try:
        return CameraKind(kind)
    except ValueError as exc:
        raise CamerasServiceError(f"invalid camera kind: {kind!r}") from exc


async def _printer_exists(session: AsyncSession, printer_id: uuid.UUID) -> bool:
    return (
        await session.execute(select(Printer.id).where(Printer.id == printer_id))
    ).scalar_one_or_none() is not None


async def _get_by_printer(session: AsyncSession, printer_id: uuid.UUID) -> Camera | None:
    stmt = select(Camera).where(Camera.printer_id == printer_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def get_for_printer(session: AsyncSession, printer_id: uuid.UUID) -> Camera:
    camera = await _get_by_printer(session, printer_id)
    if camera is None:
        raise CameraNotFoundError(str(printer_id))
    return camera


async def upsert(
    session: AsyncSession,
    *,
    printer_id: uuid.UUID,
    kind: str | CameraKind,
    snapshot_url: str,
    username: str | None = None,
    password_secret: str | None = None,
    is_active: bool = True,
    actor_user_id: uuid.UUID | None,
) -> Camera:
    """Idempotent set-or-replace. Returns the resulting Camera row.

    The 1:1 invariant is enforced by ``UNIQUE(printer_id)``; this helper
    chooses replace-semantics over reject so callers can re-POST the
    config form without first having to DELETE.
    """
    if not await _printer_exists(session, printer_id):
        raise PrinterNotFoundForCameraError(str(printer_id))

    kind_value = _coerce_kind(kind)
    snapshot_url = snapshot_url.strip()
    if not snapshot_url:
        raise CamerasServiceError("snapshot_url is required")
    username_norm = (username or "").strip() or None
    password_secret_norm = (password_secret or "").strip() or None

    existing = await _get_by_printer(session, printer_id)

    if existing is None:
        camera = Camera(
            printer_id=printer_id,
            kind=kind_value,
            snapshot_url=snapshot_url,
            username=username_norm,
            password_secret=password_secret_norm,
            is_active=is_active,
        )
        session.add(camera)
        await session.flush()
        await _emit(
            session,
            event_type=production_events.TYPE_CAMERA_CONFIGURED,
            aggregate_id=camera.id,
            payload={
                "camera_id": str(camera.id),
                "printer_id": str(printer_id),
                "kind": kind_value.value,
                "snapshot_url": snapshot_url,
            },
            actor_user_id=actor_user_id,
        )
        return camera

    # Update path — build diff with secret sentinel.
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    def _redact(field: str, value: Any) -> Any:
        if field == "password_secret" and value is not None:
            return SECRET_SENTINEL
        if isinstance(value, CameraKind):
            return value.value
        return value

    changes: dict[str, Any] = {
        "kind": kind_value,
        "snapshot_url": snapshot_url,
        "username": username_norm,
        "password_secret": password_secret_norm,
        "is_active": is_active,
    }
    for field, new_value in changes.items():
        current = getattr(existing, field)
        if current == new_value:
            continue
        before[field] = _redact(field, current)
        after[field] = _redact(field, new_value)
        setattr(existing, field, new_value)

    if not before:
        return existing

    await session.flush()
    await _emit(
        session,
        event_type=production_events.TYPE_CAMERA_UPDATED,
        aggregate_id=existing.id,
        payload={
            "camera_id": str(existing.id),
            "printer_id": str(printer_id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return existing


async def delete_for_printer(
    session: AsyncSession,
    *,
    printer_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    camera = await _get_by_printer(session, printer_id)
    if camera is None:
        raise CameraNotFoundError(str(printer_id))
    camera_id = camera.id
    await session.delete(camera)
    await session.flush()
    await _emit(
        session,
        event_type=production_events.TYPE_CAMERA_DELETED,
        aggregate_id=camera_id,
        payload={
            "camera_id": str(camera_id),
            "printer_id": str(printer_id),
        },
        actor_user_id=actor_user_id,
    )


# ---------------------------------------------------------------------------
# Snapshot proxy
# ---------------------------------------------------------------------------


# Per-process snapshot cache. Keyed on camera_id; each entry holds the
# bytes and the monotonic_time at which we cached them. Scoping note:
# this is a plain in-process dict — one container = one cache. We
# deliberately keep this dead simple; if multi-instance polling becomes
# the bottleneck the next move is a shared Redis/pgmq cache, not a more
# clever in-process scheme.
_SNAPSHOT_CACHE: dict[uuid.UUID, tuple[bytes, float]] = {}


def _clear_snapshot_cache() -> None:
    """Test hook. Not exported."""
    _SNAPSHOT_CACHE.clear()


# Transport hook for tests. Production code leaves this ``None`` so a
# real ``httpx.AsyncClient`` is used.
_TEST_TRANSPORT: httpx.BaseTransport | None = None


def _set_test_transport(transport: httpx.BaseTransport | None) -> None:
    """Install a test transport that intercepts the upstream HTTP call.

    Wiring this through a module-level hook keeps ``fetch_snapshot``'s
    signature small and avoids leaking httpx-mock-knowledge into the
    router.
    """
    global _TEST_TRANSPORT
    _TEST_TRANSPORT = transport


async def fetch_snapshot(camera_id: uuid.UUID, *, session: AsyncSession) -> bytes:
    """Fetch a single JPEG frame from the configured camera.

    Cached in-process for ``SNAPSHOT_CACHE_TTL_SECONDS`` seconds keyed
    on ``camera_id`` so dashboard polling doesn't produce N concurrent
    upstream fetches.

    v1 only supports ``kind="go2rtc"`` end-to-end. Other kinds raise
    :class:`UnsupportedCameraKindError`; the router maps that to 501.
    """
    cached = _SNAPSHOT_CACHE.get(camera_id)
    if cached is not None:
        body, cached_at = cached
        if (time.monotonic() - cached_at) < SNAPSHOT_CACHE_TTL_SECONDS:
            return body

    camera = (
        await session.execute(select(Camera).where(Camera.id == camera_id))
    ).scalar_one_or_none()
    if camera is None:
        raise CameraNotFoundError(str(camera_id))

    if camera.kind != CameraKind.GO2RTC:
        raise UnsupportedCameraKindError(
            f"snapshot proxy not implemented for kind {camera.kind.value!r}"
        )

    auth: tuple[str, str] | None = None
    if camera.username and camera.password_secret:
        auth = (camera.username, camera.password_secret)

    transport_kwarg: dict[str, Any] = {}
    if _TEST_TRANSPORT is not None:
        transport_kwarg["transport"] = _TEST_TRANSPORT

    try:
        async with httpx.AsyncClient(
            auth=auth, timeout=httpx.Timeout(5.0), **transport_kwarg
        ) as client:
            resp = await client.get(camera.snapshot_url)
            resp.raise_for_status()
            body = resp.content
    except httpx.HTTPError as exc:
        raise CameraUpstreamError(f"upstream snapshot fetch failed: {exc}") from exc

    _SNAPSHOT_CACHE[camera_id] = (body, time.monotonic())
    return body


__all__ = [
    "CameraNotFoundError",
    "CameraUpstreamError",
    "CamerasServiceError",
    "PrinterNotFoundForCameraError",
    "SECRET_SENTINEL",
    "SNAPSHOT_CACHE_TTL_SECONDS",
    "UnsupportedCameraKindError",
    "delete_for_printer",
    "fetch_snapshot",
    "get_for_printer",
    "upsert",
]
