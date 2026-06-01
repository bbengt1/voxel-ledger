"""Shared recipe-hash + migration-marker constants (epic #267, Phase 7a).

Two historical plates are the *same* Part iff their print recipe is
identical (locked decision #1: exact recipe hash). The hash is computed
over the recipe fields only — never the plate name, job, or run counts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

# Marker keys stashed in Part.custom_fields so re-runs + reverse can find
# migration-derived parts without a schema change.
RECIPE_HASH_KEY = "migration_recipe_hash"
ORIGIN_KEY = "migration_origin"
ORIGIN_VALUE = "assembly_line"

_PLACEHOLDER_NS = uuid.UUID("a55e3b1e-0000-4000-8000-000000000001")


def recipe_hash(
    *,
    parts_per_set: int,
    print_minutes: int,
    setup_minutes: int,
    print_grams_by_material: dict[Any, Any] | None,
    assigned_printer_ids: list[Any] | None,
) -> str:
    """Stable sha256 over the print recipe. Material/printer ids are
    stringified + sorted so ordering never changes the hash."""
    grams = {str(k): str(v) for k, v in (print_grams_by_material or {}).items()}
    payload = {
        "parts_per_set": int(parts_per_set),
        "print_minutes": int(print_minutes),
        "setup_minutes": int(setup_minutes),
        "grams": dict(sorted(grams.items())),
        "printers": sorted(str(p) for p in (assigned_printer_ids or [])),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plate_recipe_hash(plate: Any) -> str:
    return recipe_hash(
        parts_per_set=plate.parts_per_set,
        print_minutes=plate.print_minutes,
        setup_minutes=plate.print_hours_setup_minutes,
        print_grams_by_material=plate.print_grams_by_material,
        assigned_printer_ids=plate.assigned_printer_ids,
    )


def placeholder_part_id(recipe: str) -> uuid.UUID:
    """Deterministic stand-in id for a not-yet-created part, used only in
    dry-run so downstream steps can still build a plan."""
    return uuid.uuid5(_PLACEHOLDER_NS, recipe)


__all__ = [
    "ORIGIN_KEY",
    "ORIGIN_VALUE",
    "RECIPE_HASH_KEY",
    "placeholder_part_id",
    "plate_recipe_hash",
    "recipe_hash",
]
