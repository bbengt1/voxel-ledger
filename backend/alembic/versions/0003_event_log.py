"""event log core

Creates the append-only ``event`` table, supporting indexes, and (on
Postgres) the immutability trigger that blocks UPDATE/DELETE. SQLite
(used by tests) skips the trigger — application code never mutates event
rows anyway, and the immutability assertion is covered by an integration
test that runs against real Postgres.

Revision ID: 0003_event_log
Revises: 0002_auth
Create Date: 2026-05-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_event_log"
down_revision: str | None = "0002_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


IMMUTABILITY_FN = "event_log_block_mutation"
IMMUTABILITY_TRIGGER = "event_log_block_mutation_trg"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    payload_type = JSONB() if is_pg else sa.JSON()

    op.create_table(
        "event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "position",
            sa.BigInteger(),
            nullable=False,
            unique=True,
            autoincrement=True,
        ),
        sa.Column("type", sa.String(length=255), nullable=False),
        sa.Column("aggregate_type", sa.String(length=255), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("causation_id", sa.Uuid(), nullable=True),
        sa.Column("prev_event_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    op.create_index("ix_event_position", "event", ["position"], unique=True)
    op.create_index(
        "ix_event_aggregate",
        "event",
        ["aggregate_type", "aggregate_id", "position"],
    )
    op.create_index("ix_event_type_position", "event", ["type", "position"])
    op.create_index("ix_event_correlation_id", "event", ["correlation_id"])

    if is_pg:
        # Name the bigserial sequence explicitly so the EventStore can
        # call nextval('event_position_seq') without scraping pg_catalog.
        # Alembic's BigInteger+autoincrement on PG creates an identity
        # sequence with a generated name; rebind to our preferred name.
        op.execute("CREATE SEQUENCE IF NOT EXISTS event_position_seq " "OWNED BY event.position")
        op.execute(
            "ALTER TABLE event ALTER COLUMN position " "SET DEFAULT nextval('event_position_seq')"
        )
        # Sync the new sequence past any existing rows (none on first run,
        # but keep the migration idempotent if it's re-applied).
        op.execute(
            "SELECT setval('event_position_seq', "
            "COALESCE((SELECT MAX(position) FROM event), 0) + 1, false)"
        )

        # Immutability: raise on any UPDATE or DELETE on event rows.
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {IMMUTABILITY_FN}()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'event log is append-only (op=%, position=%)',
                    TG_OP, COALESCE(OLD.position, NEW.position);
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {IMMUTABILITY_TRIGGER}
            BEFORE UPDATE OR DELETE ON event
            FOR EACH ROW EXECUTE FUNCTION {IMMUTABILITY_FN}();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute(f"DROP TRIGGER IF EXISTS {IMMUTABILITY_TRIGGER} ON event")
        op.execute(f"DROP FUNCTION IF EXISTS {IMMUTABILITY_FN}()")

    op.drop_index("ix_event_correlation_id", table_name="event")
    op.drop_index("ix_event_type_position", table_name="event")
    op.drop_index("ix_event_aggregate", table_name="event")
    op.drop_index("ix_event_position", table_name="event")
    op.drop_table("event")

    if is_pg:
        op.execute("DROP SEQUENCE IF EXISTS event_position_seq")
