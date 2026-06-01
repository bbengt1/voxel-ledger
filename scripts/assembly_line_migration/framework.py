"""Framework: step result, context, orchestrator (epic #267, Phase 7a).

Unlike ``scripts/v1_migration`` (v1→v2, empty target), this backfill runs
**in place** on the live database. The orchestrator runs every registered
step in order inside a **single transaction**: on dry-run (the default)
it rolls back; on ``--commit`` it commits only if every step succeeded.
Steps share a mutable ``state`` dict so ``derive_parts`` can publish the
recipe-hash → part-id map that ``product_boms`` and ``repoint_jobs``
consume.

Every step is **idempotent** (re-running skips already-migrated rows) and
the engine is **non-destructive** (it never edits historical ledger rows
or deletes existing data) — so ``reverse`` (see ``reverse.py``) can cleanly
undo a commit, and material-BOM-line conversions are surfaced as
review items rather than auto-deleted.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


class MigrationError(Exception):
    """Halts the orchestrator."""


@dataclass
class StepResult:
    context: str
    rows_in: int = 0
    rows_out: int = 0
    rows_skipped: int = 0  # idempotent re-run: already-present rows
    # Conservative-by-default: anything ambiguous (non-trivial plate→part
    # ratios, uncovered material lines, multi-plate open jobs) is surfaced
    # here for a human to resolve before cutover — never guessed.
    review_items: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class BackfillResult:
    started_at: datetime
    finished_at: datetime
    dry_run: bool
    results: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def review_items(self) -> list[str]:
        out: list[str] = []
        for r in self.results:
            out.extend(r.review_items)
        return out

    def summary(self) -> str:
        lines = [
            f"assembly-line backfill {'(DRY-RUN)' if self.dry_run else '(COMMIT)'} "
            f"started={self.started_at.isoformat()} "
            f"finished={self.finished_at.isoformat()} "
            f"status={'ok' if self.ok else 'FAILED'}"
        ]
        for r in self.results:
            lines.append(
                f"  {r.context:16s}  "
                f"in={r.rows_in:>6}  out={r.rows_out:>6}  "
                f"skipped={r.rows_skipped:>6}  "
                f"review={len(r.review_items):>4}  "
                f"errors={len(r.errors)}"
            )
        review = self.review_items
        if review:
            lines.append(f"  -- {len(review)} item(s) need manual review before cutover --")
            for item in review:
                lines.append(f"     * {item}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "dry_run": self.dry_run,
            "ok": self.ok,
            "results": [asdict(r) for r in self.results],
        }


@dataclass
class StepContext:
    session: AsyncSession
    dry_run: bool = True
    actor_user_id: uuid.UUID | None = None
    # Cross-step shared data (e.g. recipe-hash → part-id map).
    state: dict[str, Any] = field(default_factory=dict)


StepFn = Callable[[StepContext], Awaitable[StepResult]]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegisteredStep:
    name: str
    fn: StepFn


_REGISTRY: list[RegisteredStep] = []


def register(name: str) -> Callable[[StepFn], StepFn]:
    def decorator(fn: StepFn) -> StepFn:
        _REGISTRY.append(RegisteredStep(name=name, fn=fn))
        return fn

    return decorator


def registered_steps() -> list[RegisteredStep]:
    return list(_REGISTRY)


def _import_contexts() -> None:
    """Import every step module so they self-register (in order)."""
    from scripts.assembly_line_migration import contexts

    _ = contexts


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def run_all(
    *,
    session: AsyncSession,
    dry_run: bool = True,
    only: list[str] | None = None,
    actor_user_id: uuid.UUID | None = None,
    report_dir: Path | None = None,
) -> BackfillResult:
    """Run registered steps in order, atomically.

    Dry-run (default) rolls back; commit persists only if every step is
    error-free. Halts on the first failing step.
    """
    _import_contexts()

    started = datetime.now(UTC)
    state: dict[str, Any] = {}
    results: list[StepResult] = []
    for entry in registered_steps():
        if only and entry.name not in only:
            continue
        ctx = StepContext(
            session=session,
            dry_run=dry_run,
            actor_user_id=actor_user_id,
            state=state,
        )
        log.info("assembly_line_migration.start", extra={"context": entry.name})
        try:
            result = await entry.fn(ctx)
        except Exception as exc:
            result = StepResult(context=entry.name)
            result.errors.append(f"{exc.__class__.__name__}: {exc}")
        results.append(result)
        if not result.ok:
            log.error("assembly_line_migration.failed", extra={"context": entry.name})
            break

    # Atomic: commit only on a fully-successful commit run; otherwise discard.
    out_ok = all(r.ok for r in results)
    if out_ok and not dry_run:
        await session.commit()
    else:
        await session.rollback()

    finished = datetime.now(UTC)
    out = BackfillResult(
        started_at=started,
        finished_at=finished,
        dry_run=dry_run,
        results=results,
    )

    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        path = report_dir / f"assembly_line_backfill_{stamp}.json"
        path.write_text(json.dumps(out.to_dict(), indent=2))
        log.info("assembly_line_migration.report_written", extra={"path": str(path)})

    return out


__all__ = [
    "BackfillResult",
    "MigrationError",
    "RegisteredStep",
    "StepContext",
    "StepFn",
    "StepResult",
    "register",
    "registered_steps",
    "run_all",
]
