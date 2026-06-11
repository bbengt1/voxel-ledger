"""GL archive manifest — the audit record of a local-ledger export (#318, Phase 5a).

Phase 5 decommissions the local general ledger: QBO becomes the sole system of
record and the GL tables are dropped. Before any destructive step, the local
books MUST be exported to durable storage (the system-of-record-of-last-resort
and the down-migration recovery path — see ``docs/quickbooks_phase0_findings.md``
§11, owner-approved 2026-06-08).

One row per archive run. It records *what* was exported (per-table row counts),
*where* (the artifact directory), an integrity fingerprint (per-file SHA-256),
and the trial-balance snapshot totals as of the cutover date — so the later
decommission gate (Phase 5c) can assert "a balanced archive exists" before the
GL is removed. The CSV/JSON artifacts themselves live on durable storage, not in
this table; this is the manifest that points at them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class GlArchiveManifest(Base):
    __tablename__ = "gl_archive_manifest"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Books are archived "as of" this date; the trial-balance snapshot closes here.
    cutover_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    # Durable-storage directory the CSV + manifest.json artifacts were written to.
    artifact_dir: Mapped[str] = mapped_column(String(1024), nullable=False)
    # {table_name: row_count} for each exported GL table.
    row_counts: Mapped[dict] = mapped_column(_JSON, nullable=False)
    # {filename: sha256-hex} integrity fingerprint of each written artifact.
    checksums: Mapped[dict] = mapped_column(_JSON, nullable=False)
    # Trial-balance snapshot totals as of ``cutover_date`` (the integrity check).
    total_debits: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    total_credits: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balanced: Mapped[bool] = mapped_column(Boolean, nullable=False)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
