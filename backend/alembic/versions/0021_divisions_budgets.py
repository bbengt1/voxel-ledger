"""division + budget tables, journal_line.division_id (Phase 4.5, #68)

Creates the ``division`` aggregate (light CRUD with partial-unique-when-
active ``code``) and the ``budget`` slot keyed by
``(account_id, division_id, period_id)``. Also adds the optional
``division_id`` column on ``journal_line`` so postings can carry the
second analytical dimension.

Uniqueness asymmetry
--------------------
The ``budget`` unique constraint is dialect-aware:

* **PostgreSQL 15+**: ``UNIQUE (account_id, division_id, period_id) NULLS
  NOT DISTINCT`` so a row with ``division_id IS NULL`` (the catch-all
  budget per account/period) is genuinely unique. We can't express that
  through the SQLAlchemy DDL DSL — it's emitted via raw SQL.
* **SQLite**: plain ``UNIQUE`` constraint. SQLite treats NULLs as
  distinct, so two rows with ``(account, NULL, period)`` won't collide
  at the DB level. The ``BudgetsService.set`` upsert path queries for an
  existing NULL-division row first and updates it in place, keeping the
  service-side check authoritative on SQLite.

Booleans use ``sa.false()`` for ``server_default`` (#49). No new ENUM
types are introduced.

Revision ID: 0021_divisions_budgets
Revises: 0020_approvals
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_divisions_budgets"
down_revision: str | None = "0020_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        "division",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
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
        "ux_division_code_active",
        "division",
        ["code"],
        unique=True,
        sqlite_where=sa.text("is_archived = 0"),
        postgresql_where=sa.text("is_archived = false"),
    )

    # On PG we'll attach NULLS NOT DISTINCT via raw ALTER below. On
    # SQLite we declare a plain UniqueConstraint inline at create-table
    # time (SQLite doesn't support ALTER TABLE ADD CONSTRAINT, and
    # NULLS NOT DISTINCT doesn't exist there anyway — the service-side
    # guard in BudgetsService.set is authoritative for the NULL case).
    budget_table_args: list[sa.schema.SchemaItem] = [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "division_id",
            sa.Uuid(),
            sa.ForeignKey("division.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "period_id",
            sa.Uuid(),
            sa.ForeignKey("accounting_period.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
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
        sa.CheckConstraint("amount >= 0", name="ck_budget_amount_nonneg"),
    ]
    if not is_pg:
        budget_table_args.append(
            sa.UniqueConstraint(
                "account_id",
                "division_id",
                "period_id",
                name="ux_budget_account_division_period",
            )
        )
    op.create_table("budget", *budget_table_args)
    op.create_index("ix_budget_period_account", "budget", ["period_id", "account_id"])
    op.create_index("ix_budget_division", "budget", ["division_id"])

    if is_pg:
        # PG 15+ supports NULLS NOT DISTINCT on unique constraints, which
        # we need so the catch-all budget (division_id NULL) is unique
        # per (account, period).
        op.execute(
            "ALTER TABLE budget ADD CONSTRAINT ux_budget_account_division_period "
            "UNIQUE NULLS NOT DISTINCT (account_id, division_id, period_id)"
        )

    # journal_line gets an optional division_id (Phase 4.5 integration).
    # The PG journal_line immutability trigger forbids any UPDATE/DELETE,
    # so we don't need to teach it about the new column — rows are
    # written once with their division_id and never touched again.
    with op.batch_alter_table("journal_line") as batch:
        batch.add_column(
            sa.Column(
                "division_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "division.id",
                    ondelete="RESTRICT",
                    name="fk_journal_line_division_id",
                ),
                nullable=True,
            )
        )
    op.create_index("ix_journal_line_division", "journal_line", ["division_id"])


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # Drop the supporting index before the column goes away, regardless
    # of dialect. Alembic's SQLite batch-mode reflection would otherwise
    # try to recreate the index on the new (column-less) table and fail.
    op.drop_index("ix_journal_line_division", table_name="journal_line")
    with op.batch_alter_table("journal_line") as batch:
        if is_pg:
            batch.drop_constraint("fk_journal_line_division_id", type_="foreignkey")
        batch.drop_column("division_id")

    if is_pg:
        # SQLite never had a separately-attached unique constraint to
        # drop — it was declared inline on the CREATE TABLE — and
        # ``drop_table`` below disposes of it. On PG the constraint was
        # added via ALTER; drop it explicitly so the downgrade is clean
        # even if a future migration depends on the table still existing.
        op.drop_constraint("ux_budget_account_division_period", "budget", type_="unique")
    op.drop_index("ix_budget_division", table_name="budget")
    op.drop_index("ix_budget_period_account", table_name="budget")
    op.drop_table("budget")

    op.drop_index("ux_division_code_active", table_name="division")
    op.drop_table("division")
