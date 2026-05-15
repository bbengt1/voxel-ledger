"""production_order + production_order_job tables (Phase 5.5, #81)

Creates the ``production_order`` + ``production_order_job`` tables plus
the ``production_order_state`` PG enum.

Per ops convention (see #49 / agents.md PG strict-typing gotcha #1), the
enum is NOT pre-created. ``op.create_table`` autocreates the PG type via
the column's dialect hook; on SQLite the same ``sa.Enum`` renders as
``VARCHAR + CHECK``.

Boolean defaults use ``sa.false()`` / ``sa.true()`` per the same guide.
(No boolean columns on this slice, but the convention is honored across
all new migrations.)

The "one-active-membership-per-job" invariant is NOT enforced at the DB
level; the service layer checks it. See model docstring for rationale.

Revision ID: 0025_production_orders
Revises: 0024_printer_history
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_production_orders"
down_revision: str | None = "0024_printer_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PRODUCTION_ORDER_STATE_VALUES = (
    "planning",
    "active",
    "completed",
    "archived",
)


def upgrade() -> None:
    production_order_state_enum = sa.Enum(
        *PRODUCTION_ORDER_STATE_VALUES, name="production_order_state"
    )

    op.create_table(
        "production_order",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_number", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "state",
            production_order_state_enum,
            nullable=False,
            server_default="planning",
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
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
        "ix_production_order_state_priority_due",
        "production_order",
        ["state", sa.text("priority DESC"), "due_at"],
    )

    op.create_table(
        "production_order_job",
        sa.Column(
            "production_order_id",
            sa.Uuid(),
            sa.ForeignKey("production_order.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("job.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_production_order_job_job_id",
        "production_order_job",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_production_order_job_job_id", table_name="production_order_job")
    op.drop_table("production_order_job")

    op.drop_index(
        "ix_production_order_state_priority_due",
        table_name="production_order",
    )
    op.drop_table("production_order")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*PRODUCTION_ORDER_STATE_VALUES, name="production_order_state").drop(
            bind, checkfirst=True
        )
