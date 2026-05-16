"""Merge the three Phase 7 parallel migration heads.

Phases 7.4 (#120, ``0036_pay_credits``), 7.5 (#123, ``0037_recur_inv``)
and 7.7 (#121, ``0039_email``) all shipped in parallel and each chained
its ``down_revision`` directly onto ``0035_invoices``. Alembic ended up
with three heads, which means ``alembic upgrade head`` will refuse to
run with::

    ERROR [alembic.util.messaging] Multiple head revisions are present
    for given argument 'head'

This migration is an empty merge — it has three ``down_revisions`` and
no schema changes. After it runs the graph is linear again with a
single head at ``0040_merge_heads``, and the next Phase 7 migration
(``0040_late_fees`` from PR #122, which will be renumbered to ``0041``
in its rebase) chains cleanly onto it.

Revision ID: 0040_merge_heads
Revises: 0036_pay_credits, 0037_recur_inv, 0039_email
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0040_merge_heads"
down_revision: tuple[str, ...] = (
    "0036_pay_credits",
    "0037_recur_inv",
    "0039_email",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op — this is a graph-merge migration only."""
    pass


def downgrade() -> None:
    """No-op — downgrading past the merge restores the three heads."""
    pass
