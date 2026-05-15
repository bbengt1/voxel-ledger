"""account table (Phase 4.1, #64)

Creates the ``account`` table — the chart of accounts — plus the
``account_type`` PG enum, a self-referential FK on ``parent_account_id``,
a partial unique index on ``(code) WHERE is_archived = false``, and
support indexes on ``(parent_account_id)`` and ``(type, code)``.

Per ops convention (see #49), the enum is NOT pre-created. We reference
it on a column via ``sa.Enum(*VALUES, name=...)`` and let
``op.create_table`` create it through the dialect hook on PG. On SQLite
the same construct renders as ``VARCHAR + CHECK``.

Booleans use ``sa.false()`` for ``server_default`` — never integer
literals — because Postgres rejects them on Boolean columns.

Revision ID: 0017_accounts
Revises: 0016_inventory_on_hand_alerts
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_accounts"
down_revision: str | None = "0016_inventory_on_hand_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACCOUNT_TYPE_VALUES = (
    "asset",
    "liability",
    "equity",
    "revenue",
    "expense",
)


def upgrade() -> None:
    account_type_enum = sa.Enum(*ACCOUNT_TYPE_VALUES, name="account_type")

    op.create_table(
        "account",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", account_type_enum, nullable=False),
        sa.Column(
            "parent_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ux_account_code_active",
        "account",
        ["code"],
        unique=True,
        sqlite_where=sa.text("is_archived = 0"),
        postgresql_where=sa.text("is_archived = false"),
    )
    op.create_index(
        "ix_account_parent_account_id",
        "account",
        ["parent_account_id"],
    )
    op.create_index(
        "ix_account_type_code",
        "account",
        ["type", "code"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_type_code", table_name="account")
    op.drop_index("ix_account_parent_account_id", table_name="account")
    op.drop_index("ux_account_code_active", table_name="account")
    op.drop_table("account")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*ACCOUNT_TYPE_VALUES, name="account_type").drop(bind, checkfirst=True)
