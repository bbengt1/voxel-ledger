"""invoices migration stub (Phase 12.4, #206).

Filled in per the Phase 12 cutover follow-up. The orchestrator already
runs this context; the body returns an empty result so the framework
+ customer wire-up can ship and downstream contexts can land
incrementally without rebasing across each other.
"""

from __future__ import annotations

from scripts.v1_migration.framework import MigrationContext, MigrationResult, register


@register("invoices")
async def migrate(ctx: MigrationContext) -> MigrationResult:
    _ = ctx
    return MigrationResult(context="invoices")
