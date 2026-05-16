"""recurring_invoice_template + items + cadence_kind / template_state enums (Phase 7.5, #113)

Creates ``recurring_invoice_template`` and ``recurring_invoice_template_item``
plus two new PG enums (``recurring_cadence_kind``, ``recurring_template_state``).
The line-item ``kind`` column reuses the existing ``invoice_item_kind`` PG
enum (created by 0035 with ``create_type=True``).

Per agents.md gotcha #1 the new enums are NOT pre-created — ``op.create_table``
auto-creates them via the columns' dialect hook. The reused
``invoice_item_kind`` column is declared with ``create_type=False`` so we do
NOT try to re-create the type. Booleans use ``sa.false()`` per the booleans
gotcha.

Revision ID: 0037_recur_inv
Revises: 0035_invoices
Create Date: 2026-05-16 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_recur_inv"
down_revision: str | None = "0035_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RECURRING_CADENCE_KIND_VALUES = (
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "yearly",
)

RECURRING_TEMPLATE_STATE_VALUES = (
    "active",
    "paused",
    "cancelled",
)


def upgrade() -> None:
    cadence_kind_enum = sa.Enum(*RECURRING_CADENCE_KIND_VALUES, name="recurring_cadence_kind")
    template_state_enum = sa.Enum(*RECURRING_TEMPLATE_STATE_VALUES, name="recurring_template_state")
    # ``invoice_item_kind`` was created by Phase 7.3 (0035_invoices); reuse it
    # here without re-creating.
    item_kind_enum = sa.Enum(
        "product",
        "job",
        "manual",
        name="invoice_item_kind",
        create_type=False,
    )

    op.create_table(
        "recurring_invoice_template",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "customer_id",
            sa.Uuid(),
            sa.ForeignKey("customer.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("cadence_kind", cadence_kind_enum, nullable=False),
        sa.Column(
            "cadence_interval",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_issue_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "auto_issue",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "state",
            template_state_enum,
            nullable=False,
            server_default="active",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "discount_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "tax_amount",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="USD",
        ),
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
        sa.CheckConstraint(
            "cadence_interval >= 1",
            name="ck_recurring_invoice_template_cadence_interval_positive",
        ),
    )
    op.create_index(
        "ix_recurring_invoice_template_customer_id",
        "recurring_invoice_template",
        ["customer_id"],
    )
    op.create_index(
        "ix_recurring_invoice_template_state",
        "recurring_invoice_template",
        ["state"],
    )
    op.create_index(
        "ix_recurring_invoice_template_next_issue_at",
        "recurring_invoice_template",
        ["next_issue_at"],
    )
    op.create_index(
        "ix_recurring_invoice_template_created_at_id",
        "recurring_invoice_template",
        ["created_at", "id"],
    )

    op.create_table(
        "recurring_invoice_template_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("recurring_invoice_template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("kind", item_kind_enum, nullable=False),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("product.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("job.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sku_or_job_number", sa.String(length=64), nullable=True),
        sa.Column(
            "quantity",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "template_id",
            "line_number",
            name="uq_recurring_invoice_template_item_line",
        ),
        sa.CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND job_id IS NULL) OR "
            "(kind = 'job' AND job_id IS NOT NULL AND product_id IS NULL) OR "
            "(kind = 'manual' AND product_id IS NULL AND job_id IS NULL)",
            name="ck_recurring_invoice_template_item_kind_ref",
        ),
    )
    op.create_index(
        "ix_recurring_invoice_template_item_template_id",
        "recurring_invoice_template_item",
        ["template_id"],
    )
    op.create_index(
        "ix_recurring_invoice_template_item_product_id",
        "recurring_invoice_template_item",
        ["product_id"],
    )
    op.create_index(
        "ix_recurring_invoice_template_item_job_id",
        "recurring_invoice_template_item",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recurring_invoice_template_item_job_id",
        table_name="recurring_invoice_template_item",
    )
    op.drop_index(
        "ix_recurring_invoice_template_item_product_id",
        table_name="recurring_invoice_template_item",
    )
    op.drop_index(
        "ix_recurring_invoice_template_item_template_id",
        table_name="recurring_invoice_template_item",
    )
    op.drop_table("recurring_invoice_template_item")

    op.drop_index(
        "ix_recurring_invoice_template_created_at_id",
        table_name="recurring_invoice_template",
    )
    op.drop_index(
        "ix_recurring_invoice_template_next_issue_at",
        table_name="recurring_invoice_template",
    )
    op.drop_index(
        "ix_recurring_invoice_template_state",
        table_name="recurring_invoice_template",
    )
    op.drop_index(
        "ix_recurring_invoice_template_customer_id",
        table_name="recurring_invoice_template",
    )
    op.drop_table("recurring_invoice_template")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*RECURRING_TEMPLATE_STATE_VALUES, name="recurring_template_state").drop(
            bind, checkfirst=True
        )
        sa.Enum(*RECURRING_CADENCE_KIND_VALUES, name="recurring_cadence_kind").drop(
            bind, checkfirst=True
        )
