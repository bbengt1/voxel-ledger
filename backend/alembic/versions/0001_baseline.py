"""baseline

Empty baseline migration. Real schema lands with Phase 1 modules.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-13 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op baseline; subsequent migrations chain off this revision."""


def downgrade() -> None:
    """No-op."""
