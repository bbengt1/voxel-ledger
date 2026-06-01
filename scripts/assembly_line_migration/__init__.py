"""Assembly-line backfill engine (epic #267, Phase 7a).

In-place, dry-run-first, idempotent, reversible backfill that moves
existing live production data onto the Materials → Parts → Products
model:

  1. derive_parts   — derive deduped Parts from historical plate recipes
  2. product_boms   — build product→part BOM lines + flag material lines
  3. repoint_jobs   — re-point open jobs to a part_id

Run via ``python -m scripts.assembly_line_migration`` (see ``__main__``).
Mirrors the ``scripts/v1_migration`` framework but operates on a single,
non-empty (live) database rather than a v1→v2 copy.
"""
