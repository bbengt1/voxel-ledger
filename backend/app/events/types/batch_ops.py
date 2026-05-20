"""Batch operations events (Phase 11.3, #195).

One event per ``POST /api/v1/batch/commit`` call. The audit projection
materializes a single ``audit_log`` row containing the affected IDs (no
PII) so an operator can later answer "who batch-archived these
customers, and when?".
"""

from __future__ import annotations

from pydantic import BaseModel

from app.events.registry import register_event

AGGREGATE_TYPE: str = "batch_ops"

TYPE_BATCH_COMMITTED = "batch_ops.BatchCommitted"


class BatchCommittedPayload(BaseModel):
    entity: str
    action: str
    applied_ids: list[str]
    skipped_ids: list[str]
    params: dict


register_event(TYPE_BATCH_COMMITTED, BatchCommittedPayload)
