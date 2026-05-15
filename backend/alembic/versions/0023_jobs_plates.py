"""jobs + plates tables (Phase 5.2, #78)

Creates the ``job`` and ``plate`` tables plus the ``job_state`` PG enum.
Also extends the existing ``inventory_transaction_kind`` enum (introduced
in #51 / migration 0015) with a new value ``production_consumption`` so
recording a plate run can write a corresponding outbound inventory
transaction for each material consumed.

Per ops convention (see #49) new enums are NOT pre-created. We reference
``job_state`` on a column via ``sa.Enum(*VALUES, name=...)`` and let
``op.create_table`` create the PG type through its dialect hook.

ENUM extension dance
--------------------
``ALTER TYPE ... ADD VALUE`` on Postgres < 12 was non-transactional;
PG 16 still requires the statement run outside an explicit transaction
block when used inside an existing one. We use ``IF NOT EXISTS`` so the
extension is idempotent across re-runs and emit a COMMIT to flush the
DDL — Alembic auto-restarts the transaction afterwards.

On SQLite the same enum is enforced via a CHECK constraint installed
when the column was created. SQLite doesn't allow altering CHECK
constraints in place, so for the test-driver path we use
``batch_alter_table`` to recreate the constraint with the new value.

Revision ID: 0023_jobs_plates
Revises: 0022_printers_cameras
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0023_jobs_plates"
down_revision: str | None = "0022_printers_cameras"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JOB_STATE_VALUES = (
    "draft",
    "queued",
    "in_progress",
    "completed",
    "cancelled",
)

# Existing values from #51 plus the new entry. SQLite re-installs the
# full CHECK constraint; PG just adds the one new value.
INVENTORY_TRANSACTION_KIND_VALUES_NEW = (
    "production_in",
    "sale_out",
    "adjustment",
    "return_in",
    "waste",
    "receipt",
    "transfer_in",
    "transfer_out",
    "production_consumption",
)


def _json_type(is_pg: bool) -> sa.types.TypeEngine:
    return JSONB() if is_pg else sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1. Extend the existing inventory_transaction_kind enum.
    if is_pg:
        # `ALTER TYPE ADD VALUE` cannot run inside a transaction block on
        # some PG versions. PG 16 accepts it within a transaction as long
        # as the value isn't used in the same TX; idempotent IF NOT EXISTS
        # keeps re-runs safe.
        op.execute(
            "ALTER TYPE inventory_transaction_kind ADD VALUE IF NOT EXISTS 'production_consumption'"
        )
    else:
        # SQLite — recreate the CHECK constraint to allow the new value.
        with op.batch_alter_table("inventory_transaction") as batch_op:
            batch_op.alter_column(
                "kind",
                existing_type=sa.Enum(
                    "production_in",
                    "sale_out",
                    "adjustment",
                    "return_in",
                    "waste",
                    "receipt",
                    "transfer_in",
                    "transfer_out",
                    name="inventory_transaction_kind",
                ),
                type_=sa.Enum(
                    *INVENTORY_TRANSACTION_KIND_VALUES_NEW,
                    name="inventory_transaction_kind",
                ),
                existing_nullable=False,
            )

    # 2. Create the job table.
    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_number",
            sa.String(length=32),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(*JOB_STATE_VALUES, name="job_state"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("quantity_ordered", sa.Integer(), nullable=False),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "actor_user_id",
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
        sa.CheckConstraint("quantity_ordered > 0", name="ck_job_quantity_ordered_positive"),
    )

    op.create_index(
        "ix_job_state_priority_due",
        "job",
        ["state", sa.text("priority DESC"), "due_at"],
    )
    op.create_index(
        "ix_job_product_state",
        "job",
        ["product_id", "state"],
    )

    # 3. Create the plate table.
    json_type = _json_type(is_pg)

    op.create_table(
        "plate",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plate_number", sa.Integer(), nullable=False),
        sa.Column("parts_per_set", sa.Integer(), nullable=False),
        sa.Column("print_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "print_grams_by_material",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'") if is_pg else sa.text("'{}'"),
        ),
        sa.Column(
            "print_hours_setup_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "assigned_printer_ids",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'") if is_pg else sa.text("'[]'"),
        ),
        sa.Column(
            "runs_completed",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("parts_per_set > 0", name="ck_plate_parts_per_set_positive"),
        sa.CheckConstraint("print_minutes >= 0", name="ck_plate_print_minutes_nonneg"),
        sa.CheckConstraint(
            "print_hours_setup_minutes >= 0",
            name="ck_plate_print_hours_setup_minutes_nonneg",
        ),
        sa.CheckConstraint("runs_completed >= 0", name="ck_plate_runs_completed_nonneg"),
        sa.UniqueConstraint("job_id", "plate_number", name="uq_plate_job_id_plate_number"),
    )

    op.create_index("ix_plate_job_id", "plate", ["job_id"])


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.drop_index("ix_plate_job_id", table_name="plate")
    op.drop_table("plate")

    op.drop_index("ix_job_product_state", table_name="job")
    op.drop_index("ix_job_state_priority_due", table_name="job")
    op.drop_table("job")

    if is_pg:
        sa.Enum(*JOB_STATE_VALUES, name="job_state").drop(bind, checkfirst=True)
        # PG does not support dropping a value from an enum. We document
        # this limitation: re-applying the migration on a fresh DB is
        # round-trip clean because the upgrade is idempotent. For an
        # in-place downgrade, the spare ``production_consumption`` value
        # remains in the enum until the type is dropped wholesale (which
        # would require migration 0015 to be downgraded too).
    else:
        # SQLite — restore the original CHECK constraint without the new
        # value.
        with op.batch_alter_table("inventory_transaction") as batch_op:
            batch_op.alter_column(
                "kind",
                existing_type=sa.Enum(
                    *INVENTORY_TRANSACTION_KIND_VALUES_NEW,
                    name="inventory_transaction_kind",
                ),
                type_=sa.Enum(
                    "production_in",
                    "sale_out",
                    "adjustment",
                    "return_in",
                    "waste",
                    "receipt",
                    "transfer_in",
                    "transfer_out",
                    name="inventory_transaction_kind",
                ),
                existing_nullable=False,
            )
