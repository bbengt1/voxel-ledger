"""Import every step module in registration order so they self-register
on the framework registry (epic #267, Phase 7a)."""

from __future__ import annotations

from scripts.assembly_line_migration.contexts import (  # noqa: F401
    derive_parts,
    product_boms,
    repoint_jobs,
)
