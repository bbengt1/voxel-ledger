"""QBO local-account map: local Account → QBO Account id (#316, epic #312).

Complements ``qbo_account_map`` (role→account) for the two posting sites that
hit arbitrary accounts with no fixed role: inter-account transfers and the bank
auto-matcher.

Revision ID: 0083_qbo_local_account_map
Revises: 0082_qbo_cdc_drift
Create Date: 2026-06-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0083_qbo_local_account_map"
down_revision: str | None = "0082_qbo_cdc_drift"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "qbo_local_account_map",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("qbo_account_id", sa.String(length=64), nullable=False),
        sa.Column("qbo_account_name", sa.String(length=255), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("account_id", name="uq_qbo_local_account_map_account"),
    )


def downgrade() -> None:
    op.drop_table("qbo_local_account_map")
