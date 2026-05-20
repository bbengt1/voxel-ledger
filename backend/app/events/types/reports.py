"""Reports event types (Phase 10.7, #182).

Today this carries only the AI-insights pipeline. Other reports
(P&L, BS, CF, TB, etc.) are pure reads and emit nothing.

CRITICAL PII RULE
-----------------
``narrative`` is LLM-generated free-text and MUST NEVER be whitelisted
into the audit excerpt. Excerpts denormalize ``(scope, period_start,
period_end, status, model)`` only — see
``app/projections/audit/excerpts.py``.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.events.registry import register_event


class _ReportsPayloadBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


AGGREGATE_TYPE_AI_INSIGHT: str = "ai_insight_summary"


class AiInsightRequestedPayload(_ReportsPayloadBase):
    summary_id: uuid.UUID
    scope: str
    period_start: str
    period_end: str


class AiInsightReadyPayload(_ReportsPayloadBase):
    summary_id: uuid.UUID
    scope: str
    period_start: str
    period_end: str
    model: str | None = None


class AiInsightFailedPayload(_ReportsPayloadBase):
    summary_id: uuid.UUID
    scope: str
    period_start: str
    period_end: str
    error: str


TYPE_AI_INSIGHT_REQUESTED = "reports.AiInsightRequested"
TYPE_AI_INSIGHT_READY = "reports.AiInsightReady"
TYPE_AI_INSIGHT_FAILED = "reports.AiInsightFailed"


register_event(TYPE_AI_INSIGHT_REQUESTED, AiInsightRequestedPayload)
register_event(TYPE_AI_INSIGHT_READY, AiInsightReadyPayload)
register_event(TYPE_AI_INSIGHT_FAILED, AiInsightFailedPayload)
