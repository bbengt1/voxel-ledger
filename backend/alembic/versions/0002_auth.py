"""auth tables

Creates `user` and `refresh_token` for Phase 0.7. Roles are stored as a
PG enum named `role`; SQLite (used by tests) falls back to a CHECK
constraint with the same values.

Revision ID: 0002_auth
Revises: 0001_baseline
Create Date: 2026-05-13 00:00:01.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE_VALUES = ("owner", "bookkeeper", "production", "sales", "viewer")


def upgrade() -> None:
    # Let SQLAlchemy auto-create the `role` enum type via op.create_table.
    # We deliberately do NOT pre-create it: when the migration crashed mid-way
    # in an earlier shape, the explicit `.create(checkfirst=True)` raced with
    # op.create_table's own (checkfirst=False) auto-create on PG, producing
    # `DuplicateObjectError: type "role" already exists`. create_type=False
    # on the column type was not honored by the dialect-level hook.
    bind = op.get_bind()
    role_enum = sa.Enum(*ROLE_VALUES, name="role")

    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("role", role_enum, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true") if bind.dialect.name == "postgresql" else sa.text("1"),
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

    op.create_table(
        "refresh_token",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column(
            "parent_token_id",
            sa.Uuid(),
            sa.ForeignKey("refresh_token.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_refresh_token_user_id", "refresh_token", ["user_id"])
    op.create_index("ix_refresh_token_family_id", "refresh_token", ["family_id"])
    op.create_index(
        "ix_refresh_token_token_hash",
        "refresh_token",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_token_token_hash", table_name="refresh_token")
    op.drop_index("ix_refresh_token_family_id", table_name="refresh_token")
    op.drop_index("ix_refresh_token_user_id", table_name="refresh_token")
    op.drop_table("refresh_token")
    op.drop_table("user")

    # On PG the user table teardown should auto-drop the `role` enum,
    # but we drop it explicitly with checkfirst to be idempotent if the
    # auto-drop ever stops firing the way auto-create did in upgrade.
    # On SQLite (tests) the enum is a CHECK constraint and vanishes with
    # the table — the dialect guard keeps the drop PG-only.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*ROLE_VALUES, name="role").drop(bind, checkfirst=True)
