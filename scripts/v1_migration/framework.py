"""Framework: result type, context, orchestrator (Phase 12.4, #206)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.event import Event
from app.schemas.events import EventCreate
from app.services import event_store
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


class MigrationError(Exception):
    """Halts the orchestrator."""


@dataclass
class MigrationResult:
    context: str
    rows_in: int = 0
    rows_out: int = 0
    rows_skipped: int = 0  # idempotent re-run: already-present rows
    events_emitted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class OrchestratorResult:
    started_at: datetime
    finished_at: datetime
    dry_run: bool
    results: list[MigrationResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def summary(self) -> str:
        lines = [
            f"v1 migration {'(DRY-RUN)' if self.dry_run else ''} "
            f"started={self.started_at.isoformat()} "
            f"finished={self.finished_at.isoformat()} "
            f"status={'ok' if self.ok else 'failed'}"
        ]
        for r in self.results:
            lines.append(
                f"  {r.context:24s}  "
                f"in={r.rows_in:>6}  out={r.rows_out:>6}  "
                f"skipped={r.rows_skipped:>6}  "
                f"events={r.events_emitted:>6}  "
                f"errors={len(r.errors)}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "dry_run": self.dry_run,
            "results": [asdict(r) for r in self.results],
        }


@dataclass
class MigrationContext:
    """Per-context entry-point arguments."""

    v1_session: Any  # v1 DB session, type-unconstrained for now
    v2_session: AsyncSession
    dry_run: bool = False
    actor_user_id: uuid.UUID | None = None


MigrateFn = Callable[[MigrationContext], Awaitable[MigrationResult]]


async def emit_backfill_event(
    *,
    session: AsyncSession,
    type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    original_occurred_at: datetime,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    """Append a backfill event with ``schema_version=0``.

    ``occurred_at`` carries the v1 source row's original timestamp so
    period-based reports stay accurate. ``recorded_at`` is the live
    migration run-time, set by the event store.
    """
    await event_store.append(
        EventCreate(
            type=type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=original_occurred_at,
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            schema_version=0,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


async def check_preconditions(
    *, v2_session: AsyncSession, allow_prod: bool = False
) -> None:
    """Raise MigrationError if the target DB is unsuitable.

    Today's contract: v2 must be **empty** (no events). The
    ``--allow-prod`` flag is required to run against a non-localhost
    DSN (operator opt-in for the live cutover).
    """
    count = int(
        (
            await v2_session.execute(select(func.count()).select_from(Event))
        ).scalar_one()
    )
    if count > 0:
        raise MigrationError(
            f"v2 event log is not empty ({count} events). Migration is "
            "idempotent on natural identity but the orchestrator refuses "
            "to start over a non-empty log."
        )
    if not allow_prod:
        bind = v2_session.bind
        if bind is None or bind.url is None:
            return
        host = bind.url.host or ""
        if host not in {"", "localhost", "127.0.0.1", "db"}:
            raise MigrationError(
                f"refusing to run against non-local host {host!r} without "
                "--allow-prod"
            )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredContext:
    name: str
    fn: MigrateFn


# Filled by individual context modules at import time.
_REGISTRY: list[RegisteredContext] = []


def register(name: str) -> Callable[[MigrateFn], MigrateFn]:
    def decorator(fn: MigrateFn) -> MigrateFn:
        _REGISTRY.append(RegisteredContext(name=name, fn=fn))
        return fn

    return decorator


def registered_contexts() -> list[RegisteredContext]:
    return list(_REGISTRY)


def _import_contexts() -> None:
    """Import every context module so they self-register."""
    from scripts.v1_migration import contexts

    _ = contexts


async def run_all(
    *,
    v1_session: Any,
    v2_session: AsyncSession,
    dry_run: bool = False,
    only: list[str] | None = None,
    actor_user_id: uuid.UUID | None = None,
    audit_log_dir: Path | None = None,
    allow_prod: bool = False,
) -> OrchestratorResult:
    """Run every registered context in registration order.

    Halts on the first context that returns an error-bearing result.
    Writes a JSON audit log to ``audit_log_dir`` if provided.
    """
    _import_contexts()
    await check_preconditions(v2_session=v2_session, allow_prod=allow_prod)

    started = datetime.now(UTC)
    results: list[MigrationResult] = []
    for entry in registered_contexts():
        if only and entry.name not in only:
            continue
        ctx = MigrationContext(
            v1_session=v1_session,
            v2_session=v2_session,
            dry_run=dry_run,
            actor_user_id=actor_user_id,
        )
        log.info("v1_migration.start", extra={"context": entry.name})
        try:
            result = await entry.fn(ctx)
        except Exception as exc:
            result = MigrationResult(context=entry.name)
            result.errors.append(f"{exc.__class__.__name__}: {exc}")
        results.append(result)
        if not result.ok:
            log.error("v1_migration.failed", extra={"context": entry.name})
            break
        if not dry_run:
            await v2_session.commit()
        else:
            await v2_session.rollback()
    finished = datetime.now(UTC)

    out = OrchestratorResult(
        started_at=started,
        finished_at=finished,
        dry_run=dry_run,
        results=results,
    )

    if audit_log_dir is not None:
        audit_log_dir.mkdir(parents=True, exist_ok=True)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        path = audit_log_dir / f"v1_migration_{stamp}.json"
        path.write_text(json.dumps(out.to_dict(), indent=2))
        log.info("v1_migration.audit_written", extra={"path": str(path)})

    return out


__all__ = [
    "MigrationContext",
    "MigrationError",
    "MigrationResult",
    "OrchestratorResult",
    "check_preconditions",
    "emit_backfill_event",
    "register",
    "registered_contexts",
    "run_all",
]
