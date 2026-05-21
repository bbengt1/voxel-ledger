"""v1 -> v2 one-shot data migration (Phase 12.4, #206).

One module per bounded context exposes ``migrate(...)``. The
orchestrator runs them in dependency order, halts on any error, and
writes a JSON audit log for the cutover record.

Per-event invariants for backfill (matches Phase 1.1 event-log
contract):

- ``schema_version=0`` on every backfilled event so it's
  distinguishable from live appends going forward.
- ``recorded_at`` = migration run-time (now); ``occurred_at`` = the
  v1 source row's original timestamp (creation or last update).
- Idempotent: re-running on a populated v2 DB is a no-op. Modules
  pre-check by natural identity (customer_number, vendor_number, ...)
  and skip rows already present.
"""

from scripts.v1_migration.framework import (
    MigrationContext,
    MigrationError,
    MigrationResult,
    OrchestratorResult,
    run_all,
)

__all__ = [
    "MigrationContext",
    "MigrationError",
    "MigrationResult",
    "OrchestratorResult",
    "run_all",
]
