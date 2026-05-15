"""Cost engine (Phase 5.3, #79).

Two-layer module: a pure-function calculator (``calculator``) that takes
a snapshot of all cost inputs plus the proposed plate shape and returns a
fully-broken-down :class:`CalcResult`, and a thin service layer
(``service``) that loads that snapshot from the DB and delegates.

The pure layer is deterministic over ``(CalcInputs, CalcContext)`` —
no DB access, no I/O, Decimal-only math. The service layer owns context
loading from Phase 4.5 rates (with Phase 1.5 settings fallback) and is
the only part that touches the session.
"""

from app.services.cost_engine.calculator import (
    CalcContext,
    CalcInputs,
    CalcResult,
    PerPlateCost,
    PlateInput,
    calculate,
)
from app.services.cost_engine.service import (
    CostEngineService,
    MissingRateConfigError,
)

__all__ = [
    "CalcContext",
    "CalcInputs",
    "CalcResult",
    "CostEngineService",
    "MissingRateConfigError",
    "PerPlateCost",
    "PlateInput",
    "calculate",
]
