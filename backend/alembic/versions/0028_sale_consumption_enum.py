"""sale_consumption inventory_transaction_kind enum value (Phase 6.3, #95)

Extends the existing ``inventory_transaction_kind`` PG enum (created in
#51 / migration 0015 and extended in #78 / migration 0023 with
``production_consumption``) with a new value ``sale_consumption``. The
COGS posting flow in :mod:`app.services.cogs.service` emits one
``inventory_transaction`` per consumed FIFO lot when a sale is
confirmed; the rows are tagged ``sale_consumption`` so a downstream
replay can distinguish "drawn down by a posted sale" from a manual
``sale_out`` adjustment.

ENUM extension dance — see #78 and agents.md PG strict-typing gotcha #2:

* On Postgres we ``ALTER TYPE ... ADD VALUE IF NOT EXISTS`` so the
  extension is idempotent across re-runs. PG cannot drop an enum value
  in place, so the downgrade is intentionally empty (re-applying the
  upgrade against a fresh DB is round-trip clean; an in-place rollback
  leaves the spare value in the type until 0015 is downgraded
  wholesale).
* On SQLite the same enum is enforced via a CHECK constraint installed
  with the column. SQLite doesn't allow altering CHECK constraints in
  place, so we use ``batch_alter_table`` to recreate it with the new
  value.

Revision ID: 0028_sale_consumption_enum
Revises: 0027_sales
Create Date: 2026-05-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_sale_consumption_enum"
down_revision: str | None = "0027_sales"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INVENTORY_TRANSACTION_KIND_VALUES_PRIOR = (
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

INVENTORY_TRANSACTION_KIND_VALUES_NEW = (
    *INVENTORY_TRANSACTION_KIND_VALUES_PRIOR,
    "sale_consumption",
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute(
            "ALTER TYPE inventory_transaction_kind ADD VALUE IF NOT EXISTS 'sale_consumption'"
        )
    else:
        with op.batch_alter_table("inventory_transaction") as batch_op:
            batch_op.alter_column(
                "kind",
                existing_type=sa.Enum(
                    *INVENTORY_TRANSACTION_KIND_VALUES_PRIOR,
                    name="inventory_transaction_kind",
                ),
                type_=sa.Enum(
                    *INVENTORY_TRANSACTION_KIND_VALUES_NEW,
                    name="inventory_transaction_kind",
                ),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        # PG cannot drop an enum value safely. Re-applying on a fresh DB
        # is idempotent; an in-place downgrade leaves the spare value in
        # place until the enum type is dropped wholesale.
        return

    with op.batch_alter_table("inventory_transaction") as batch_op:
        batch_op.alter_column(
            "kind",
            existing_type=sa.Enum(
                *INVENTORY_TRANSACTION_KIND_VALUES_NEW,
                name="inventory_transaction_kind",
            ),
            type_=sa.Enum(
                *INVENTORY_TRANSACTION_KIND_VALUES_PRIOR,
                name="inventory_transaction_kind",
            ),
            existing_nullable=False,
        )
