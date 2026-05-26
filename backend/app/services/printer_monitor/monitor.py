"""Lazy-loaded printer monitor implementation (Phase 5.4).

Per-printer ``asyncio.Task`` polls the printer's Moonraker endpoint via
a pluggable probe callable. Defaults to :func:`_default_probe`, which
does a short-timeout HTTP GET against ``/printer/objects/query`` —
Moonraker exposes this over HTTP-on-the-same-host as the WS feed, and
treating the HTTP poll as the source of liveness lets the monitor stay
single-protocol while still satisfying the < 5 s freshness budget
(``agents.md`` performance budgets).

Tests substitute the probe via :func:`set_probe_factory` so unit tests
don't depend on real network or websockets.

State machine
-------------
On each tick:

- probe success → derive ``PrinterState.state`` from Moonraker output;
  if the previous state was ``disconnected`` we additionally append a
  ``connected`` history row.
- probe failure → mark ``state="disconnected"``; append a
  ``disconnected`` history row IFF the previous state was not already
  ``disconnected`` (per-disconnection, NOT per-retry).
- detected transition between ``idle`` ↔ ``printing`` ↔ ``paused`` ↔
  ``error`` appends a matching ``print_*`` history row.

Backoff is per-printer, exponential, capped at 60 s. Logging is loud
on the first failure (ERROR) and quiet thereafter (DEBUG) until a
success resets the counter.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import db as db_module
from app.events.types import production as production_events
from app.models.printer import Printer
from app.models.printer_history_event import PrinterEventKind, PrinterHistoryEvent
from app.schemas.events import EventCreate
from app.services import event_store

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS: float = 5.0
BACKOFF_INITIAL_SECONDS: float = 2.0
BACKOFF_MAX_SECONDS: float = 60.0
PROBE_TIMEOUT_SECONDS: float = 4.0


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PrinterState:
    """In-memory state cache for a single printer."""

    printer_id: uuid.UUID
    state: str = "disconnected"
    progress_pct: float | None = None
    elapsed_seconds: int | None = None
    remaining_seconds_estimate: int | None = None
    current_file: str | None = None
    temperatures: dict[str, float | None] = field(
        default_factory=lambda: {"extruder": None, "bed": None}
    )
    # Live print telemetry (gcode_move / motion_report / print_stats).
    speed_mm_s: float | None = None
    flow_mm3_s: float | None = None
    filament_used_mm: float | None = None
    current_layer: int | None = None
    total_layers: int | None = None
    last_seen_at: datetime | None = None


@dataclass
class ProbeResult:
    """Result of a single Moonraker probe.

    ``ok=False`` means we treat the printer as disconnected this tick.
    """

    ok: bool
    state: str = "disconnected"
    progress_pct: float | None = None
    elapsed_seconds: int | None = None
    remaining_seconds_estimate: int | None = None
    current_file: str | None = None
    extruder_temp: float | None = None
    bed_temp: float | None = None
    speed_mm_s: float | None = None
    flow_mm3_s: float | None = None
    filament_used_mm: float | None = None
    current_layer: int | None = None
    total_layers: int | None = None


ProbeFn = Callable[[str, str | None], Awaitable[ProbeResult]]
"""``async def probe(url: str, api_key: str | None) -> ProbeResult``."""


# ---------------------------------------------------------------------------
# Default probe — short-timeout HTTP GET against /printer/objects/query.
# ---------------------------------------------------------------------------


async def _default_probe(url: str, api_key: str | None) -> ProbeResult:
    """Single Moonraker probe. Returns ``ok=False`` on any error."""
    import httpx

    query = (
        "print_stats=state,filename,print_duration,filament_used,info"
        "&display_status=progress"
        "&extruder=temperature"
        "&heater_bed=temperature"
        "&virtual_sdcard=progress"
        "&gcode_move=speed,speed_factor,extrude_factor"
        "&motion_report=live_position,live_velocity,live_extruder_velocity"
    )
    target = url.rstrip("/") + "/printer/objects/query?" + query
    headers: dict[str, str] = {}
    if api_key:
        headers["X-Api-Key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(target, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return ProbeResult(ok=False)

    status = data.get("result", {}).get("status", {})
    print_stats = status.get("print_stats", {}) or {}
    display = status.get("display_status", {}) or {}
    extruder = status.get("extruder", {}) or {}
    bed = status.get("heater_bed", {}) or {}
    gcode_move = status.get("gcode_move", {}) or {}
    motion = status.get("motion_report", {}) or {}

    moonraker_state = (print_stats.get("state") or "").lower()
    mapped = _map_moonraker_state(moonraker_state)
    progress = display.get("progress")
    progress_pct = float(progress) * 100.0 if isinstance(progress, int | float) else None

    elapsed = print_stats.get("print_duration")
    elapsed_seconds = int(elapsed) if isinstance(elapsed, int | float) else None
    remaining = None
    if elapsed_seconds is not None and progress and progress > 0:
        remaining = int(elapsed_seconds * (1.0 - progress) / progress)

    # Live speed: prefer motion_report.live_velocity (mm/s), fall back to
    # gcode_move.speed (mm/min → mm/s) scaled by speed_factor.
    speed_mm_s = _as_float(motion.get("live_velocity"))
    if speed_mm_s is None:
        raw_speed = _as_float(gcode_move.get("speed"))
        factor = _as_float(gcode_move.get("speed_factor"))
        if raw_speed is not None and factor is not None:
            speed_mm_s = raw_speed * factor / 60.0
        elif raw_speed is not None:
            speed_mm_s = raw_speed / 60.0

    # Flow ≈ live_extruder_velocity × π × (filament_radius_mm)² with
    # 1.75 mm filament (r=0.875). live_extruder_velocity is mm/s of
    # filament; convert to mm³/s of plastic.
    extruder_vel = _as_float(motion.get("live_extruder_velocity"))
    flow_mm3_s = None
    if extruder_vel is not None:
        # π × 0.875² ≈ 2.4053 mm² cross-section for 1.75 mm filament.
        flow_mm3_s = extruder_vel * 2.4053

    filament_used_mm = _as_float(print_stats.get("filament_used"))
    info = print_stats.get("info") or {}
    current_layer = info.get("current_layer")
    total_layers = info.get("total_layer")
    current_layer_int = int(current_layer) if isinstance(current_layer, int | float) else None
    total_layers_int = int(total_layers) if isinstance(total_layers, int | float) else None

    return ProbeResult(
        ok=True,
        state=mapped,
        progress_pct=progress_pct,
        elapsed_seconds=elapsed_seconds,
        remaining_seconds_estimate=remaining,
        current_file=print_stats.get("filename") or None,
        extruder_temp=_as_float(extruder.get("temperature")),
        bed_temp=_as_float(bed.get("temperature")),
        speed_mm_s=speed_mm_s,
        flow_mm3_s=flow_mm3_s,
        filament_used_mm=filament_used_mm,
        current_layer=current_layer_int,
        total_layers=total_layers_int,
    )


def _map_moonraker_state(value: str) -> str:
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
# Singleton plumbing
# ---------------------------------------------------------------------------


_monitor: PrinterMonitor | None = None
_monitor_lock: asyncio.Lock | None = None
_probe_factory: ProbeFn = _default_probe


def set_probe_factory(probe: ProbeFn) -> None:
    """Override the probe used by future monitor instances.

    Tests use this to substitute a deterministic async function for the
    HTTP probe. Calling this does not affect an already-constructed
    monitor — call :func:`stop_monitor` first.
    """
    global _probe_factory
    _probe_factory = probe


def _get_lock() -> asyncio.Lock:
    global _monitor_lock
    if _monitor_lock is None:
        _monitor_lock = asyncio.Lock()
    return _monitor_lock


async def get_monitor() -> PrinterMonitor:
    """Return the singleton monitor, constructing it on first call.

    Idempotent: subsequent calls return the same instance.
    """
    global _monitor
    lock = _get_lock()
    async with lock:
        if _monitor is None:
            session_factory = db_module._session_factory
            if session_factory is None:
                raise RuntimeError("session factory not initialized; cannot start printer monitor")
            mon = PrinterMonitor(session_factory=session_factory, probe=_probe_factory)
            await mon.start()
            _monitor = mon
        return _monitor


async def stop_monitor() -> None:
    """Cancel all monitor tasks and drop the singleton."""
    global _monitor
    lock = _get_lock()
    async with lock:
        if _monitor is None:
            return
        await _monitor.stop()
        _monitor = None


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class PrinterMonitor:
    """Owns one ``asyncio.Task`` per printer with a non-null
    ``moonraker_url`` and a thread-safe in-memory ``PrinterState`` cache.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        probe: ProbeFn,
    ) -> None:
        self._session_factory = session_factory
        self._probe = probe
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._states: dict[uuid.UUID, PrinterState] = {}
        self._refresh_events: dict[uuid.UUID, asyncio.Event] = {}
        self._printer_meta: dict[uuid.UUID, tuple[str, str | None]] = {}
        self._lock = asyncio.Lock()
        self._stopping = False

    # -- lifecycle ----------------------------------------------------

    async def start(self) -> None:
        """Discover printers with ``moonraker_url`` set and spawn a task
        per printer. Safe to call when zero printers qualify."""
        async with self._session_factory() as session:
            stmt = select(Printer).where(
                Printer.moonraker_url.is_not(None),
                Printer.is_archived.is_(False),
            )
            result = await session.execute(stmt)
            printers = list(result.scalars().all())

        for printer in printers:
            self._states[printer.id] = PrinterState(printer_id=printer.id)
            self._refresh_events[printer.id] = asyncio.Event()
            self._printer_meta[printer.id] = (
                printer.moonraker_url or "",
                printer.moonraker_api_key,
            )
            self._tasks[printer.id] = asyncio.create_task(
                self._run(printer.id), name=f"printer-monitor-{printer.id}"
            )

    async def stop(self) -> None:
        self._stopping = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()

    # -- public accessors ---------------------------------------------

    def get_state(self, printer_id: uuid.UUID) -> PrinterState | None:
        return self._states.get(printer_id)

    def get_ws_health(
        self, *, freshness_seconds: float = 30.0
    ) -> tuple[bool, datetime | None]:
        """Aggregate "is any printer's status fresh?" + the most-recent
        ``last_seen_at`` across all monitored printers.

        Used by the Control Center to render the ``ws_health`` tile.
        Returns ``(connected, last_event_at)`` where ``connected`` means
        at least one monitored printer reported a status within the
        freshness window.
        """
        most_recent: datetime | None = None
        for state in self._states.values():
            if state.last_seen_at is None:
                continue
            if most_recent is None or state.last_seen_at > most_recent:
                most_recent = state.last_seen_at
        if most_recent is None:
            return False, None
        delta = (datetime.now(UTC) - most_recent).total_seconds()
        return delta <= freshness_seconds, most_recent

    def force_refresh(self, printer_id: uuid.UUID) -> bool:
        """Trigger an out-of-band probe. Returns True if the printer is
        being monitored, False otherwise."""
        event = self._refresh_events.get(printer_id)
        if event is None:
            return False
        event.set()
        return True

    @property
    def printers_monitored(self) -> int:
        return len(self._tasks)

    # -- per-printer task ---------------------------------------------

    async def _run(self, printer_id: uuid.UUID) -> None:
        backoff = BACKOFF_INITIAL_SECONDS
        consecutive_failures = 0
        url, api_key = self._printer_meta[printer_id]
        refresh = self._refresh_events[printer_id]
        try:
            while True:
                try:
                    result = await self._probe(url, api_key)
                except Exception:
                    result = ProbeResult(ok=False)

                await self._apply_probe(printer_id, result)

                if result.ok:
                    consecutive_failures = 0
                    backoff = BACKOFF_INITIAL_SECONDS
                    interval = POLL_INTERVAL_SECONDS
                else:
                    consecutive_failures += 1
                    if consecutive_failures == 1:
                        log.error(
                            "printer_monitor.probe_failed printer_id=%s url=%s",
                            printer_id,
                            url,
                        )
                    else:
                        log.debug(
                            "printer_monitor.probe_failed printer_id=%s url=%s " "consecutive=%d",
                            printer_id,
                            url,
                            consecutive_failures,
                        )
                    interval = backoff
                    backoff = min(backoff * 2.0, BACKOFF_MAX_SECONDS)

                # Wait for next tick OR a force_refresh signal.
                refresh.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(refresh.wait(), timeout=interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("printer_monitor.task_crashed printer_id=%s", printer_id)

    # -- state application + history ----------------------------------

    async def _apply_probe(self, printer_id: uuid.UUID, result: ProbeResult) -> None:
        async with self._lock:
            prev = self._states.get(printer_id) or PrinterState(printer_id=printer_id)
            new_state = result.state if result.ok else "disconnected"

            updated = PrinterState(
                printer_id=printer_id,
                state=new_state,
                progress_pct=result.progress_pct if result.ok else prev.progress_pct,
                elapsed_seconds=result.elapsed_seconds if result.ok else prev.elapsed_seconds,
                remaining_seconds_estimate=(
                    result.remaining_seconds_estimate
                    if result.ok
                    else prev.remaining_seconds_estimate
                ),
                current_file=result.current_file if result.ok else prev.current_file,
                temperatures={
                    "extruder": result.extruder_temp
                    if result.ok
                    else prev.temperatures.get("extruder"),
                    "bed": result.bed_temp if result.ok else prev.temperatures.get("bed"),
                },
                speed_mm_s=result.speed_mm_s if result.ok else prev.speed_mm_s,
                flow_mm3_s=result.flow_mm3_s if result.ok else prev.flow_mm3_s,
                filament_used_mm=(
                    result.filament_used_mm if result.ok else prev.filament_used_mm
                ),
                current_layer=result.current_layer if result.ok else prev.current_layer,
                total_layers=result.total_layers if result.ok else prev.total_layers,
                last_seen_at=datetime.now(UTC) if result.ok else prev.last_seen_at,
            )
            self._states[printer_id] = updated

            transitions = _classify_transitions(prev.state, new_state)

        if self._stopping:
            return
        for kind in transitions:
            # Shield history writes from task cancellation — a half-finished
            # flush against the (shared, single-conn) test sqlite engine
            # corrupts the connection for the next request. In production
            # the per-request engine pool sidesteps this; the shield is
            # cheap insurance either way.
            await asyncio.shield(self._record_history(printer_id, kind, updated))

    async def _record_history(
        self,
        printer_id: uuid.UUID,
        kind: PrinterEventKind,
        state: PrinterState,
    ) -> None:
        """Persist one history row + emit ``PrinterHistoryEventRecorded``."""
        try:
            session_ctx = self._session_factory()
        except Exception:
            return
        async with session_ctx as session:
            try:
                occurred_at = datetime.now(UTC)
                row = PrinterHistoryEvent(
                    id=uuid.uuid4(),
                    printer_id=printer_id,
                    event_kind=kind,
                    occurred_at=occurred_at,
                    details={
                        "state": state.state,
                        "current_file": state.current_file,
                        "progress_pct": state.progress_pct,
                    },
                )
                session.add(row)
                await session.flush()

                await event_store.append(
                    EventCreate(
                        type=production_events.TYPE_PRINTER_HISTORY_EVENT_RECORDED,
                        aggregate_type=production_events.AGGREGATE_TYPE_PRINTER,
                        aggregate_id=printer_id,
                        payload={
                            "event_id": str(row.id),
                            "printer_id": str(printer_id),
                            "event_kind": kind.value,
                            "occurred_at": occurred_at.isoformat(),
                            "details": row.details,
                        },
                        occurred_at=occurred_at,
                        correlation_id=uuid.uuid4(),
                        actor_user_id=None,
                    ),
                    session=session,
                )
                await session.commit()
            except Exception:
                log.debug(
                    "printer_monitor.history_record_failed printer_id=%s kind=%s",
                    printer_id,
                    kind,
                )
                with contextlib.suppress(Exception):
                    await session.rollback()


def _classify_transitions(prev_state: str, new_state: str) -> list[PrinterEventKind]:
    """Map a state transition to zero-or-more history event kinds."""
    if prev_state == new_state:
        return []

    transitions: list[PrinterEventKind] = []

    if prev_state == "disconnected" and new_state != "disconnected":
        transitions.append(PrinterEventKind.CONNECTED)
    if new_state == "disconnected" and prev_state != "disconnected":
        transitions.append(PrinterEventKind.DISCONNECTED)
        return transitions

    if new_state == "printing" and prev_state in ("idle", "disconnected"):
        transitions.append(PrinterEventKind.PRINT_STARTED)
    elif new_state == "paused" and prev_state == "printing":
        transitions.append(PrinterEventKind.PRINT_PAUSED)
    elif new_state == "printing" and prev_state == "paused":
        transitions.append(PrinterEventKind.PRINT_RESUMED)
    elif new_state == "idle" and prev_state == "printing":
        transitions.append(PrinterEventKind.PRINT_COMPLETED)
    elif new_state == "error":
        transitions.append(PrinterEventKind.PRINT_ERRORED)

    return transitions
