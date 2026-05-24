"""Public API for the Moonraker printer monitor (Phase 5.4).

CRITICAL: this module is LAZY-LOADED. It is never imported by app
startup. Importing :mod:`app.main` or :mod:`app.core.settings` MUST NOT
import any name from here. The first call to :func:`get_monitor`
constructs the singleton and starts the per-printer poll tasks. App boot
succeeds even when every Moonraker host is unreachable — this is the
explicit invariant the v1 incident codified into the v2 plan
(``IMPLEMENTATION_PLAN.md`` Phase 5 + ``agents.md`` Known Risks).

Three layers verify the invariant:

1. A unit test asserts ``sys.modules`` does NOT contain
   ``app.services.printer_monitor`` after ``create_app`` + a ``/health``
   round-trip.
2. An integration test boots the app with two bogus Moonraker URLs and
   asserts the app stays healthy and the state endpoint returns either
   ``503 monitor_warming_up`` or ``200`` with ``state="disconnected"``.
3. This very docstring + the matching comment in ``app/main.py``'s
   lifespan callback.

Public surface:

* :func:`get_monitor` — async idempotent singleton accessor; the first
  call wires the per-printer tasks against the current process's
  session factory.
* :func:`stop_monitor` — admin restart hook; cancels every running
  task and drops the singleton.
* :class:`PrinterMonitor` — exposed for type hints + tests.
* :class:`PrinterState` — the cache record shape.
"""

from __future__ import annotations

from app.services.printer_monitor.monitor import (
    PrinterMonitor,
    PrinterState,
    get_monitor,
    set_probe_factory,
    stop_monitor,
)
from app.services.printer_monitor.ws import (
    MoonrakerWsClient,
    StatusUpdate,
    WsStatus,
)

__all__ = [
    "MoonrakerWsClient",
    "PrinterMonitor",
    "PrinterState",
    "StatusUpdate",
    "WsStatus",
    "get_monitor",
    "set_probe_factory",
    "stop_monitor",
]
