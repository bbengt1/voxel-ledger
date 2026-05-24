"""Moonraker WebSocket client (Issue #222).

One persistent JSON-RPC 2.0 connection per printer. On connect, the
client subscribes to ``printer.objects`` for ``print_stats`` +
``display_status`` + temperature objects, then dispatches every
``notify_status_update`` notification to the registered async
callback. The callback is what the existing monitor uses to refresh
its in-memory ``PrinterState`` cache, so endpoints (and the Control
Center) keep reading from the same surface they always have — the
data just arrives via push instead of HTTP poll.

This module is **pluggable** at three seams so it stays unit-
testable without a real websocket server:

  - ``WsClientFactory`` — the type alias for the
    ``async def connect(url, *, headers) -> Connection`` callable.
    Production uses :func:`_default_connect_factory` (built on the
    ``websockets`` library); tests inject a fake.
  - ``Connection`` protocol — minimal surface
    (``send``, ``__aiter__``, ``close``); easy to mock.
  - The :class:`MoonrakerWsClient` itself never blocks app boot —
    it owns one asyncio task that's spawned lazily from the
    monitor's first refresh.

Reconnect: exponential backoff up to 60s, jittered ±20%. Failures
are logged loudly on the first disconnect, then quietly on
subsequent retries until a fresh connect resets the counter.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

log = logging.getLogger(__name__)


SUBSCRIBE_OBJECTS: dict[str, list[str] | None] = {
    "print_stats": ["state", "filename", "print_duration"],
    "display_status": ["progress"],
    "extruder": ["temperature"],
    "heater_bed": ["temperature"],
    "virtual_sdcard": ["progress"],
}

OPEN_TIMEOUT_SECONDS = 10.0
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 60.0
JITTER_FRACTION = 0.2


# ---------------------------------------------------------------------------
# Pluggable transport
# ---------------------------------------------------------------------------


class Connection(Protocol):
    """Minimal duck-typed surface we need from a websockets connection."""

    async def send(self, payload: str) -> None: ...

    def __aiter__(self) -> AsyncIterator[str | bytes]: ...

    async def close(self) -> None: ...


WsClientFactory = Callable[..., Awaitable[Connection]]
"""``async def connect(url, *, headers=None, open_timeout=...) -> Connection``."""


async def _default_connect_factory(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    open_timeout: float = OPEN_TIMEOUT_SECONDS,
) -> Connection:
    """Production factory: thin shim over ``websockets.connect``.

    Returns the same context-manager-style connection the rest of
    this module treats as a :class:`Connection`. The shim only exists
    so tests can swap in a deterministic in-memory transport without
    monkeypatching ``websockets``.
    """
    import websockets  # local import keeps the module importable when websockets is absent

    connect_kwargs: dict[str, Any] = {"open_timeout": open_timeout}
    if headers:
        connect_kwargs["additional_headers"] = headers
    return await websockets.connect(url, **connect_kwargs)


# ---------------------------------------------------------------------------
# Status snapshot
# ---------------------------------------------------------------------------


@dataclass
class WsStatus:
    connected: bool = False
    last_event_at: datetime | None = None
    last_error: str | None = None
    reconnect_count: int = 0


# ---------------------------------------------------------------------------
# Notification payload (what we hand to the callback)
# ---------------------------------------------------------------------------


@dataclass
class StatusUpdate:
    printer_id: uuid.UUID
    received_at: datetime
    raw: dict[str, Any] = field(default_factory=dict)

    # Derived convenience fields (each may be None if the notification
    # only partially updated objects, which is the normal Moonraker
    # delta-update behavior).
    state: str | None = None
    progress_pct: float | None = None
    current_file: str | None = None
    elapsed_seconds: int | None = None
    extruder_temp: float | None = None
    bed_temp: float | None = None

    @classmethod
    def from_moonraker(
        cls, *, printer_id: uuid.UUID, payload: dict[str, Any]
    ) -> StatusUpdate:
        print_stats = payload.get("print_stats") or {}
        display = payload.get("display_status") or {}
        extruder = payload.get("extruder") or {}
        bed = payload.get("heater_bed") or {}
        virt = payload.get("virtual_sdcard") or {}

        state_raw = (print_stats.get("state") or "").lower() or None
        state = _map_moonraker_state(state_raw) if state_raw is not None else None
        progress = display.get("progress")
        if progress is None:
            progress = virt.get("progress")
        progress_pct = (
            float(progress) * 100.0 if isinstance(progress, int | float) else None
        )
        elapsed = print_stats.get("print_duration")
        elapsed_seconds = int(elapsed) if isinstance(elapsed, int | float) else None
        return cls(
            printer_id=printer_id,
            received_at=datetime.now(UTC),
            raw=payload,
            state=state,
            progress_pct=progress_pct,
            current_file=print_stats.get("filename") or None,
            elapsed_seconds=elapsed_seconds,
            extruder_temp=_as_float(extruder.get("temperature")),
            bed_temp=_as_float(bed.get("temperature")),
        )


def _map_moonraker_state(value: str | None) -> str | None:
    if value is None:
        return None
    if value in ("printing",):
        return "printing"
    if value in ("paused",):
        return "paused"
    if value in ("error",):
        return "error"
    if value in ("standby", "complete", "cancelled", "idle"):
        return "idle"
    return "idle"


def _as_float(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


OnStatusFn = Callable[[StatusUpdate], Awaitable[None]]


class MoonrakerWsClient:
    """One WS connection per printer + an async task that reconnects
    on failure with exponential backoff.

    Lifecycle:

      - Construct (no I/O).
      - ``await client.start()`` — spawns the reconnect/listen task.
        Idempotent; calling twice is a no-op.
      - ``await client.stop()`` — cancels the task and closes the
        active connection if any.
      - ``client.status`` — current :class:`WsStatus`. Read-only.
    """

    def __init__(
        self,
        *,
        printer_id: uuid.UUID,
        ws_url: str,
        api_key: str | None,
        on_status: OnStatusFn,
        connect_factory: WsClientFactory | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.printer_id = printer_id
        self.ws_url = ws_url
        self.api_key = api_key
        self._on_status = on_status
        self._connect_factory: WsClientFactory = (
            connect_factory or _default_connect_factory
        )
        self._rng = rng or random.Random()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._current: Connection | None = None
        self.status = WsStatus()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(
            self._run(), name=f"moonraker-ws-{self.printer_id}"
        )

    async def stop(self) -> None:
        self._stopping = True
        current = self._current
        self._current = None
        if current is not None:
            with contextlib.suppress(Exception):
                await current.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None

    # ---- internal loop -------------------------------------------------

    async def _run(self) -> None:
        backoff = BACKOFF_INITIAL_SECONDS
        consecutive_failures = 0
        try:
            while not self._stopping:
                try:
                    headers = (
                        {"X-Api-Key": self.api_key} if self.api_key else None
                    )
                    ws = await self._connect_factory(
                        self.ws_url,
                        headers=headers,
                        open_timeout=OPEN_TIMEOUT_SECONDS,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.status = WsStatus(
                        connected=False,
                        last_event_at=self.status.last_event_at,
                        last_error=str(exc) or exc.__class__.__name__,
                        reconnect_count=self.status.reconnect_count,
                    )
                    consecutive_failures += 1
                    if consecutive_failures == 1:
                        log.error(
                            "moonraker_ws.connect_failed printer_id=%s url=%s err=%s",
                            self.printer_id,
                            self.ws_url,
                            exc,
                        )
                    else:
                        log.debug(
                            "moonraker_ws.connect_failed printer_id=%s consecutive=%d",
                            self.printer_id,
                            consecutive_failures,
                        )
                    await self._sleep_with_jitter(backoff)
                    backoff = min(backoff * 2.0, BACKOFF_MAX_SECONDS)
                    continue

                self._current = ws
                consecutive_failures = 0
                backoff = BACKOFF_INITIAL_SECONDS
                self.status = WsStatus(
                    connected=True,
                    last_event_at=self.status.last_event_at,
                    last_error=None,
                    reconnect_count=self.status.reconnect_count + 1,
                )
                log.info("moonraker_ws.connected printer_id=%s", self.printer_id)

                try:
                    await self._subscribe(ws)
                    await self._listen(ws)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning(
                        "moonraker_ws.disconnected printer_id=%s err=%s",
                        self.printer_id,
                        exc,
                    )
                finally:
                    with contextlib.suppress(Exception):
                        await ws.close()
                    self._current = None
                    self.status = WsStatus(
                        connected=False,
                        last_event_at=self.status.last_event_at,
                        last_error=None,
                        reconnect_count=self.status.reconnect_count,
                    )
                if self._stopping:
                    return
                await self._sleep_with_jitter(backoff)
                backoff = min(backoff * 2.0, BACKOFF_MAX_SECONDS)
        except asyncio.CancelledError:
            raise

    async def _subscribe(self, ws: Connection) -> None:
        request = {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {"objects": dict(SUBSCRIBE_OBJECTS)},
            "id": 1,
        }
        await ws.send(json.dumps(request))

    async def _listen(self, ws: Connection) -> None:
        async for raw_msg in ws:
            if isinstance(raw_msg, bytes):
                raw_msg = raw_msg.decode("utf-8", errors="replace")
            try:
                msg = json.loads(raw_msg)
            except json.JSONDecodeError:
                log.debug(
                    "moonraker_ws.bad_json printer_id=%s len=%d",
                    self.printer_id,
                    len(raw_msg),
                )
                continue
            await self._handle(msg)

    async def _handle(self, msg: dict[str, Any]) -> None:
        # JSON-RPC notification: {"jsonrpc":"2.0","method":"notify_status_update",
        #                         "params":[{<objects>}, eventtime]}
        if msg.get("method") != "notify_status_update":
            return
        params = msg.get("params") or []
        if not params or not isinstance(params[0], dict):
            return
        update = StatusUpdate.from_moonraker(
            printer_id=self.printer_id, payload=params[0]
        )
        self.status = WsStatus(
            connected=True,
            last_event_at=update.received_at,
            last_error=None,
            reconnect_count=self.status.reconnect_count,
        )
        try:
            await self._on_status(update)
        except Exception:
            log.exception(
                "moonraker_ws.on_status_failed printer_id=%s", self.printer_id
            )

    async def _sleep_with_jitter(self, seconds: float) -> None:
        if seconds <= 0:
            return
        delta = seconds * JITTER_FRACTION
        jittered = max(0.1, seconds + self._rng.uniform(-delta, delta))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.sleep(jittered), timeout=jittered + 1.0)


__all__ = [
    "BACKOFF_INITIAL_SECONDS",
    "BACKOFF_MAX_SECONDS",
    "Connection",
    "MoonrakerWsClient",
    "OnStatusFn",
    "OPEN_TIMEOUT_SECONDS",
    "StatusUpdate",
    "WsClientFactory",
    "WsStatus",
]
