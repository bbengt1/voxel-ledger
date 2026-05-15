"""accounting_period table (Phase 4.3, #66)

Creates the ``accounting_period`` table and the ``accounting_period_state``
PG enum, with state-machine columns plus the GiST exclusion constraint
on PG so overlapping date ranges are rejected at the DB level (the
service-layer overlap check is the primary defense; this is the safety
net). Also installs ``btree_gist`` since the constraint pairs daterange
with future UUID/text columns might join.

Per the ops convention (see #49), the enum is NOT pre-created. We
reference it on a column via ``sa.Enum(*VALUES, name=...)`` and let
``op.create_table`` create it through the dialect hook on PG. On SQLite
the same construct renders as ``VARCHAR + CHECK``.

Booleans use ``sa.false()`` for ``server_default`` — never integer
literals — because Postgres rejects them on Boolean columns. (No booleans
on this table, kept here for the standard reminder.)

After creating the table, this migration also tightens
``journal_entry.period_id`` from nullable → NOT NULL. On a fresh dev DB
there are no existing rows, so the backfill is a no-op. If any rows
exist, the migration tries to match each to a freshly-created period (a
user would have to create periods covering the dates first); rows
without a match cause a clear error so the operator can fix it before
re-running.

Revision ID: 0019_accounting_periods
Revises: 0018_journal_entries
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_accounting_periods"
down_revision: str | None = "0018_journal_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACCOUNTING_PERIOD_STATE_VALUES = (
    "open",
    "closed",
    "locked",
)

EXCLUSION_CONSTRAINT_NAME = "ex_accounting_period_no_overlap"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # The GiST exclusion below uses btree_gist for the daterange &&
        # operator. Idempotent extension install.
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    state_enum = sa.Enum(*ACCOUNTING_PERIOD_STATE_VALUES, name="accounting_period_state")

    op.create_table(
        "accounting_period",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "state",
            state_enum,
            nullable=False,
            server_default="open",
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "closed_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "locked_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.CheckConstraint(
            "end_date >= start_date",
            name="ck_accounting_period_end_after_start",
        ),
    )

    op.create_index(
        "ix_accounting_period_start_date",
        "accounting_period",
        ["start_date"],
    )
    op.create_index(
        "ix_accounting_period_end_date",
        "accounting_period",
        ["end_date"],
    )
    op.create_index(
        "ix_accounting_period_state_end_date",
        "accounting_period",
        ["state", sa.text("end_date DESC")],
    )

    if is_pg:
        # GiST exclusion constraint: reject any pair of inclusive date
        # ranges that overlap. The service check is still the primary
        # defense; this is the DB-level safety net.
        op.execute(
            f"""
            ALTER TABLE accounting_period
            ADD CONSTRAINT {EXCLUSION_CONSTRAINT_NAME}
            EXCLUDE USING gist (
                daterange(start_date, end_date, '[]') WITH &&
            )
            """
        )

    # --- Backfill + tighten journal_entry.period_id to NOT NULL --------
    # On a fresh dev DB this loop is a no-op. If rows exist, attempt to
    # match each to a freshly created period covering posted_at; rows
    # without a match abort the migration with a clear error so the
    # operator can create periods before re-running.
    je_table = sa.table(
        "journal_entry",
        sa.column("id", sa.Uuid()),
        sa.column("posted_at", sa.DateTime(timezone=True)),
        sa.column("period_id", sa.Uuid()),
    )
    ap_table = sa.table(
        "accounting_period",
        sa.column("id", sa.Uuid()),
        sa.column("start_date", sa.Date()),
        sa.column("end_date", sa.Date()),
    )

    rows = list(
        bind.execute(
            sa.select(je_table.c.id, je_table.c.posted_at).where(je_table.c.period_id.is_(None))
        )
    )
    unmatched = 0
    for je_id, posted_at in rows:
        posted_date = posted_at.date() if posted_at is not None else None
        if posted_date is None:
            unmatched += 1
            continue
        match = bind.execute(
            sa.select(ap_table.c.id).where(
                sa.and_(
                    ap_table.c.start_date <= posted_date,
                    ap_table.c.end_date >= posted_date,
                )
            )
        ).first()
        if match is None:
            unmatched += 1
            continue
        bind.execute(sa.update(je_table).where(je_table.c.id == je_id).values(period_id=match[0]))
    if unmatched:
        raise RuntimeError(
            f"found {unmatched} journal_entry rows with no matching accounting_period — "
            "create periods covering those dates before running this migration."
        )

    with op.batch_alter_table("journal_entry") as batch:
        batch.alter_column("period_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_foreign_key(
            "fk_journal_entry_period_id",
            "accounting_period",
            ["period_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    with op.batch_alter_table("journal_entry") as batch:
        batch.drop_constraint("fk_journal_entry_period_id", type_="foreignkey")
        batch.alter_column("period_id", existing_type=sa.Uuid(), nullable=True)

    if is_pg:
        op.execute(
            f"ALTER TABLE accounting_period DROP CONSTRAINT IF EXISTS {EXCLUSION_CONSTRAINT_NAME}"
        )

    op.drop_index("ix_accounting_period_state_end_date", table_name="accounting_period")
    op.drop_index("ix_accounting_period_end_date", table_name="accounting_period")
    op.drop_index("ix_accounting_period_start_date", table_name="accounting_period")
    op.drop_table("accounting_period")

    if is_pg:
        sa.Enum(*ACCOUNTING_PERIOD_STATE_VALUES, name="accounting_period_state").drop(
            bind, checkfirst=True
        )
