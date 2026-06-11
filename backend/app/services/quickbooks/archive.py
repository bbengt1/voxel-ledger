"""Local-GL archive/export for decommission (#318, epic #312, Phase 5a).

Phase 5 removes the local general ledger and drops its tables. Before any
destructive step the books must be exported to durable storage — the
system-of-record-of-last-resort and the down-migration recovery path
(``docs/quickbooks_phase0_findings.md`` §11, owner-approved 2026-06-08).

:func:`build_archive` writes a verbatim CSV dump of every GL table plus a
trial-balance snapshot as of the cutover date, fingerprints each file with
SHA-256, writes a ``manifest.json``, and persists a :class:`GlArchiveManifest`
row pointing at the artifacts. It is a pure read+export — it never mutates the
GL and is independent of ``quickbooks.enabled``.

The later decommission gate (Phase 5c) asserts a *balanced* archive exists
before the GL is removed; this service records the ``balanced`` flag but always
produces the artifacts (an unbalanced ledger is exactly what an operator needs
exported and flagged).
"""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_balance import AccountBalance
from app.models.gl_archive_manifest import GlArchiveManifest
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.services.reports import trial_balance


class ArchiveError(RuntimeError):
    """The GL archive could not be produced (e.g. the target dir is unwritable)."""


# The GL tables the archive captures. Each is exported verbatim (every column,
# every row) so the dump can reconstruct the ledger for audit / down-migration.
_GL_MODELS: tuple[tuple[str, type], ...] = (
    ("account", Account),
    ("account_balance", AccountBalance),
    ("journal_entry", JournalEntry),
    ("journal_line", JournalLine),
)

# All books postdate this; the trial-balance snapshot's lower bound so its
# closing balances reflect the entire ledger as of the cutover date.
_EPOCH = date(1970, 1, 1)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _export_table(
    session: AsyncSession, name: str, model: type, out_dir: Path
) -> tuple[int, str]:
    """Dump every row of ``model`` to ``<out_dir>/<name>.csv``; return
    ``(row_count, sha256)``. Rows are ordered by primary key for a stable,
    diffable dump."""
    columns = [c.name for c in model.__table__.columns]
    stmt = select(model).order_by(*model.__table__.primary_key.columns)
    rows = list((await session.execute(stmt)).scalars().all())
    path = out_dir / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_csv_value(getattr(row, col)) for col in columns])
    return len(rows), _sha256(path)


async def build_archive(
    session: AsyncSession,
    *,
    cutover_date: date,
    out_dir: str | Path,
    actor_user_id: uuid.UUID | None,
) -> GlArchiveManifest:
    """Export the local GL + a trial-balance snapshot to ``out_dir`` and
    persist the manifest. Caller commits."""
    target = Path(out_dir)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArchiveError(f"cannot create archive directory {target}: {exc}") from exc
    if not target.is_dir():
        raise ArchiveError(f"archive path {target} is not a directory")

    row_counts: dict[str, int] = {}
    checksums: dict[str, str] = {}
    try:
        for name, model in _GL_MODELS:
            count, digest = await _export_table(session, name, model, target)
            row_counts[name] = count
            checksums[f"{name}.csv"] = digest

        # Trial-balance snapshot as of the cutover date (include every account).
        report = await trial_balance.build(
            session, date_from=_EPOCH, date_to=cutover_date, include_zero=True
        )
        tb_path = target / "trial_balance.csv"
        tb_path.write_text(trial_balance.to_csv(report), encoding="utf-8")
        checksums["trial_balance.csv"] = _sha256(tb_path)
    except OSError as exc:
        raise ArchiveError(f"failed writing archive artifacts to {target}: {exc}") from exc

    total_debits = report.total_period_debit
    total_credits = report.total_period_credit
    balanced = total_debits == total_credits

    manifest_meta: dict[str, Any] = {
        "cutover_date": cutover_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "row_counts": row_counts,
        "checksums": checksums,
        "trial_balance": {
            "total_debits": str(total_debits),
            "total_credits": str(total_credits),
            "balanced": balanced,
            "account_count": len(report.rows),
        },
    }
    (target / "manifest.json").write_text(json.dumps(manifest_meta, indent=2), encoding="utf-8")

    manifest = GlArchiveManifest(
        cutover_date=cutover_date,
        artifact_dir=str(target),
        row_counts=row_counts,
        checksums=checksums,
        total_debits=total_debits,
        total_credits=total_credits,
        balanced=balanced,
        generated_by_user_id=actor_user_id,
    )
    session.add(manifest)
    await session.flush()
    return manifest


async def latest(session: AsyncSession) -> GlArchiveManifest | None:
    """Most recent archive manifest, or ``None`` if the GL was never archived."""
    return (
        (
            await session.execute(
                select(GlArchiveManifest).order_by(GlArchiveManifest.created_at.desc()).limit(1)
            )
        )
        .scalars()
        .first()
    )


async def list_manifests(session: AsyncSession, *, limit: int = 50) -> list[GlArchiveManifest]:
    return list(
        (
            await session.execute(
                select(GlArchiveManifest).order_by(GlArchiveManifest.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
