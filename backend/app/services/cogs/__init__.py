"""COGS service package (Phase 6.3, #95).

See :mod:`app.services.cogs.fifo` for the pure FIFO calculator and
:mod:`app.services.cogs.service` for the DB-aware service.
"""

from __future__ import annotations

from app.services.cogs.fifo import (
    CogsConsumption,
    CogsResult,
    InsufficientInventory,
    InventoryLot,
    compute_cogs,
)
from app.services.cogs.service import (
    CogsServiceError,
    MissingSalesPostingAccountError,
    PostResult,
    SaleCogsBreakdown,
    SaleLineCogs,
    post_for_sale,
    preview,
    reverse_for_sale,
)

__all__ = [
    "CogsConsumption",
    "CogsResult",
    "CogsServiceError",
    "InsufficientInventory",
    "InventoryLot",
    "MissingSalesPostingAccountError",
    "PostResult",
    "SaleCogsBreakdown",
    "SaleLineCogs",
    "compute_cogs",
    "post_for_sale",
    "preview",
    "reverse_for_sale",
]
