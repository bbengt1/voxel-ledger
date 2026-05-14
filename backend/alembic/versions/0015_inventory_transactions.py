"""inventory_transaction table (Phase 3.2, #51)

Creates the append-only ``inventory_transaction`` ledger plus two PG
ENUMs (``inventory_transaction_kind``, ``inventory_entity_kind``), the
hot-path composite indexes, and (on Postgres only) a BEFORE UPDATE OR
DELETE trigger that blocks mutation of the rows. SQLite — used by unit
tests — installs the table + indexes only; the immutability invariant
is exercised by a PG integration test.

Per ops convention (see #49) the enums are NOT pre-created. We reference
each enum on a column via ``sa.Enum(*VALUES, name=...)`` and let
``op.create_table`` create it through the dialect hook on PG. On SQLite
the same construct renders as ``VARCHAR + CHECK``.

Boolean / nullable defaults use proper SA constructs (``sa.false()`` /
``sa.func.now()``), never integer literals — Postgres rejects those on
Boolean columns (see #49).

Revision ID: 0015_inventory_transactions
Revises: 0014_inventory_locations
Create Date: 2026-05-14 00:00:05.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_inventory_transactions"
down_revision: str | None = "0014_inventory_locations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INVENTORY_TRANSACTION_KIND_VALUES = (
    "production_in",
    "sale_out",
    "adjustment",
    "return_in",
    "waste",
    "receipt",
    "transfer_in",
    "transfer_out",
)
INVENTORY_ENTITY_KIND_VALUES = ("material", "supply", "product")

IMMUTABILITY_FN = "inventory_transaction_block_mutation"
IMMUTABILITY_TRIGGER = "inventory_transaction_block_mutation_trg"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    kind_col = sa.Column(
        "kind",
        sa.Enum(*INVENTORY_TRANSACTION_KIND_VALUES, name="inventory_transaction_kind"),
        nullable=False,
    )
    entity_kind_col = sa.Column(
        "entity_kind",
        sa.Enum(*INVENTORY_ENTITY_KIND_VALUES, name="inventory_entity_kind"),
        nullable=False,
    )

    op.create_table(
        "inventory_transaction",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        kind_col,
        entity_kind_col,
        # Polymorphic ref — no FK by design (see model docstring).
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "location_id",
            sa.Uuid(),
            sa.ForeignKey("inventory_location.id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_cost_at_transaction", sa.Numeric(18, 6), nullable=True),
        sa.Column("total_cost_at_transaction", sa.Numeric(18, 6), nullable=True),
        sa.Column("transfer_pair_id", sa.Uuid(), nullable=True),
        sa.Column("linked_job_id", sa.Uuid(), nullable=True),
        sa.Column("linked_sale_id", sa.Uuid(), nullable=True),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
    )

    op.create_index(
        "ix_inventory_tx_entity_location_occurred",
        "inventory_transaction",
        ["entity_kind", "entity_id", "location_id", "occurred_at"],
    )
    op.create_index(
        "ix_inventory_tx_location_occurred",
        "inventory_transaction",
        ["location_id", "occurred_at"],
    )
    op.create_index(
        "ix_inventory_tx_kind_occurred",
        "inventory_transaction",
        ["kind", "occurred_at"],
    )
    op.create_index(
        "ix_inventory_tx_transfer_pair",
        "inventory_transaction",
        ["transfer_pair_id"],
        sqlite_where=sa.text("transfer_pair_id IS NOT NULL"),
        postgresql_where=sa.text("transfer_pair_id IS NOT NULL"),
    )

    if is_pg:
        # Immutability trigger — mirrors the event-log pattern from
        # 0003_event_log.py. The ledger is append-only at the DB layer.
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {IMMUTABILITY_FN}()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'inventory_transaction is append-only (op=%, id=%)',
                    TG_OP, COALESCE(OLD.id, NEW.id);
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {IMMUTABILITY_TRIGGER}
            BEFORE UPDATE OR DELETE ON inventory_transaction
            FOR EACH ROW EXECUTE FUNCTION {IMMUTABILITY_FN}();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute(f"DROP TRIGGER IF EXISTS {IMMUTABILITY_TRIGGER} ON inventory_transaction")
        op.execute(f"DROP FUNCTION IF EXISTS {IMMUTABILITY_FN}()")

    op.drop_index("ix_inventory_tx_transfer_pair", table_name="inventory_transaction")
    op.drop_index("ix_inventory_tx_kind_occurred", table_name="inventory_transaction")
    op.drop_index("ix_inventory_tx_location_occurred", table_name="inventory_transaction")
    op.drop_index(
        "ix_inventory_tx_entity_location_occurred",
        table_name="inventory_transaction",
    )
    op.drop_table("inventory_transaction")

    if is_pg:
        sa.Enum(
            *INVENTORY_TRANSACTION_KIND_VALUES,
            name="inventory_transaction_kind",
        ).drop(bind, checkfirst=True)
        sa.Enum(
            *INVENTORY_ENTITY_KIND_VALUES,
            name="inventory_entity_kind",
        ).drop(bind, checkfirst=True)
