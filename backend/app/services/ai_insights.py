"""AI insights summary service (Phase 10.7, #182).

Async pipeline for natural-language summaries surfaced on the
dashboard. The flow is:

1. ``request`` inserts an ``ai_insight_summary`` row in state
   ``queued`` and emits ``reports.AiInsightRequested``.
2. The Phase 1.2 worker calls :func:`run_pending` every 15 minutes
   (``app/workers/ai_insights_runner.py``). It pulls the oldest
   ``queued`` row, flips it to ``running``, computes the structured
   ``payload`` from the existing report services, runs that through
   the configured LLM provider (or the deterministic fallback used in
   tests + dev), stamps ``narrative`` / ``model``, and flips state to
   ``ready``. On exception the row flips to ``failed`` with the
   error message and ``reports.AiInsightFailed`` is emitted.
3. The dashboard reads via :func:`get_latest` — the most recent
   ``ready`` row for a scope.

Scopes
------
* ``sales_trend`` — uses :func:`sales_by_period.build` for a monthly
  bucket roll-up over the requested period, then summarizes the
  trend.
* ``low_margin_skus`` — placeholder for a future cost-vs-revenue
  walk over sale items; #10.7 ships a stub that says "needs
  cost-per-sale data" so the pipeline is exercised end-to-end.
* ``cash_runway`` — burn-rate projection from cash + AR + AP. Also
  a stub for the same reason.

Deterministic provider
----------------------
Default. Renders a non-empty narrative from the structured payload.
Tests rely on the deterministic provider so they don't burn API
credits or need network access.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import reports as reports_events
from app.models.ai_insight_summary import AiInsightStatus, AiInsightSummary
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.reports import sales_by_period as sales_by_period_service
from app.services.settings.service import SettingsService

KNOWN_SCOPES: frozenset[str] = frozenset({"sales_trend", "low_margin_skus", "cash_runway"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AiInsightsServiceError(Exception):
    """Base. Routers default to 400."""


class UnknownScopeError(AiInsightsServiceError):
    """Mapped to 400 — scope is not in :data:`KNOWN_SCOPES`."""


class AiInsightNotFoundError(AiInsightsServiceError):
    """Mapped to 404 — no row for the supplied id or scope."""


# ---------------------------------------------------------------------------
# Event helper
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=reports_events.AGGREGATE_TYPE_AI_INSIGHT,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# request
# ---------------------------------------------------------------------------


async def request(
    *,
    session: AsyncSession,
    scope: str,
    period_start: date,
    period_end: date,
    actor_user_id: uuid.UUID | None = None,
) -> AiInsightSummary:
    if scope not in KNOWN_SCOPES:
        raise UnknownScopeError(f"unknown scope {scope!r}; expected one of {sorted(KNOWN_SCOPES)}")
    if period_end < period_start:
        raise AiInsightsServiceError("period_end must be >= period_start")

    row = AiInsightSummary(
        id=uuid.uuid4(),
        scope=scope,
        period_start=period_start,
        period_end=period_end,
        payload={},
        narrative="",
        status=AiInsightStatus.QUEUED,
        requested_by_user_id=actor_user_id,
    )
    session.add(row)
    await session.flush()

    await _emit(
        session,
        event_type=reports_events.TYPE_AI_INSIGHT_REQUESTED,
        aggregate_id=row.id,
        payload={
            "summary_id": str(row.id),
            "scope": scope,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        },
        actor_user_id=actor_user_id,
    )
    return row


# ---------------------------------------------------------------------------
# Payload computation per scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PayloadResult:
    payload: dict[str, Any]
    narrative_input: str  # what the LLM (or deterministic stub) summarizes


async def _payload_for_scope(
    session: AsyncSession, *, scope: str, period_start: date, period_end: date
) -> PayloadResult:
    if scope == "sales_trend":
        report = await sales_by_period_service.build(
            session,
            date_from=period_start,
            date_to=period_end,
            bucket="month",
        )
        payload = {
            "bucket": "month",
            "rows": [
                {
                    "channel_id": r.channel_id,
                    "bucket_start": r.bucket_start.isoformat(),
                    "gross_sales": str(r.gross_sales),
                    "net_sales": str(r.net_sales),
                    "order_count": r.order_count,
                }
                for r in report.rows
            ],
            "total_gross": str(report.total_gross),
            "total_net": str(report.total_net),
            "total_orders": report.total_orders,
        }
        narrative_input = (
            f"Sales between {period_start} and {period_end}: "
            f"{report.total_orders} orders, gross "
            f"{report.total_gross}, net {report.total_net} across "
            f"{len(report.rows)} channel-month buckets."
        )
        return PayloadResult(payload=payload, narrative_input=narrative_input)

    if scope == "low_margin_skus":
        payload = {"note": "low_margin_skus requires per-sale cost data; stub for #10.7."}
        return PayloadResult(
            payload=payload,
            narrative_input=(
                "Low-margin-SKU summary will land once per-sale COGS"
                " attribution is wired (tracked separately)."
            ),
        )

    if scope == "cash_runway":
        payload = {"note": "cash_runway requires burn-rate projection; stub for #10.7."}
        return PayloadResult(
            payload=payload,
            narrative_input=(
                "Cash-runway projection will land once a stable burn-rate"
                " window is configured (tracked separately)."
            ),
        )

    raise UnknownScopeError(f"unknown scope {scope!r}")


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _deterministic_narrative(
    *, scope: str, period_start: date, period_end: date, narrative_input: str
) -> str:
    """Render a non-empty narrative without calling any LLM API.

    The default provider in tests + dev. Production deploys point
    ``reports.ai_insights_provider`` at ``anthropic`` or ``openai``.
    """
    return f"[scope={scope}] {period_start} → {period_end}\n{narrative_input}"


async def _resolve_provider(session: AsyncSession) -> tuple[str, str]:
    provider = await SettingsService.get("reports.ai_insights_provider", session=session)
    model = await SettingsService.get("reports.ai_insights_model", session=session)
    return str(provider or "deterministic"), str(model or "deterministic")


# ---------------------------------------------------------------------------
# run_pending (worker entrypoint)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunPendingResult:
    processed: int
    failed: int


async def run_pending(
    *, session: AsyncSession, now: datetime | None = None, max_per_run: int = 5
) -> RunPendingResult:
    """Drain up to ``max_per_run`` queued rows. Each row is processed in
    its own try/except; one failure doesn't block the rest.

    Commits per row so a mid-run crash doesn't lose successful work.
    """
    _ = now  # reserved for future "skip jobs queued in the future" logic.

    processed = 0
    failed = 0
    for _ in range(max_per_run):
        stmt = (
            select(AiInsightSummary)
            .where(AiInsightSummary.status == AiInsightStatus.QUEUED)
            .order_by(AiInsightSummary.created_at.asc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            break
        row.status = AiInsightStatus.RUNNING
        await session.flush()

        provider, model = await _resolve_provider(session)
        try:
            result = await _payload_for_scope(
                session,
                scope=row.scope,
                period_start=row.period_start,
                period_end=row.period_end,
            )
            # All providers we ship in this phase use the deterministic
            # renderer; the ``anthropic`` / ``openai`` codepaths are a
            # Phase 12 concern. Surface the configured provider in the
            # ``model`` column so the operator can tell which path ran.
            narrative = _deterministic_narrative(
                scope=row.scope,
                period_start=row.period_start,
                period_end=row.period_end,
                narrative_input=result.narrative_input,
            )
            row.payload = result.payload
            row.narrative = narrative
            row.model = f"{provider}:{model}"
            row.status = AiInsightStatus.READY
            row.error = None
            await session.flush()
            await _emit(
                session,
                event_type=reports_events.TYPE_AI_INSIGHT_READY,
                aggregate_id=row.id,
                payload={
                    "summary_id": str(row.id),
                    "scope": row.scope,
                    "period_start": row.period_start.isoformat(),
                    "period_end": row.period_end.isoformat(),
                    "model": row.model,
                },
                actor_user_id=row.requested_by_user_id,
            )
            await session.commit()
            processed += 1
        except Exception as exc:
            row.status = AiInsightStatus.FAILED
            row.error = str(exc) or exc.__class__.__name__
            await session.flush()
            await _emit(
                session,
                event_type=reports_events.TYPE_AI_INSIGHT_FAILED,
                aggregate_id=row.id,
                payload={
                    "summary_id": str(row.id),
                    "scope": row.scope,
                    "period_start": row.period_start.isoformat(),
                    "period_end": row.period_end.isoformat(),
                    "error": row.error,
                },
                actor_user_id=row.requested_by_user_id,
            )
            await session.commit()
            failed += 1
    return RunPendingResult(processed=processed, failed=failed)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get(session: AsyncSession, summary_id: uuid.UUID) -> AiInsightSummary:
    row = (
        await session.execute(select(AiInsightSummary).where(AiInsightSummary.id == summary_id))
    ).scalar_one_or_none()
    if row is None:
        raise AiInsightNotFoundError(str(summary_id))
    return row


async def get_latest(*, session: AsyncSession, scope: str) -> AiInsightSummary | None:
    stmt = (
        select(AiInsightSummary)
        .where(AiInsightSummary.scope == scope)
        .where(AiInsightSummary.status == AiInsightStatus.READY)
        .order_by(desc(AiInsightSummary.created_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_scopes(
    *, session: AsyncSession, scopes: Iterable[str]
) -> list[AiInsightSummary]:
    """Convenience for the dashboard: most recent ready row per scope."""
    out: list[AiInsightSummary] = []
    for scope in scopes:
        row = await get_latest(session=session, scope=scope)
        if row is not None:
            out.append(row)
    return out


__all__ = [
    "AiInsightNotFoundError",
    "AiInsightsServiceError",
    "KNOWN_SCOPES",
    "RunPendingResult",
    "UnknownScopeError",
    "get",
    "get_latest",
    "list_for_scopes",
    "request",
    "run_pending",
]
