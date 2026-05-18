"""bank match rules (Phase 8.10, #137)

Introduces the ``bank_match_rule`` aggregate — operator-defined matchers
that the auto-match worker uses to classify ``bank_transaction`` rows
into either a posted journal entry, an ``ignored`` flip, or a flagged
review.

Per agents.md gotcha #1, the three new PG enums
(``bank_match_rule_kind``, ``bank_match_field``, ``bank_match_action``)
are auto-created by ``op.create_table`` — they are NOT pre-created.
Boolean server defaults use ``sa.true()`` (gotcha "Boolean defaults").

Revision ID: 0048_bank_match_rules
Revises: 0047_bank_imports
Create Date: 2026-05-18 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_bank_match_rules"
down_revision: str | None = "0047_bank_imports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


BANK_MATCH_RULE_KIND_VALUES = ("contains", "regex", "starts_with", "equals")
BANK_MATCH_FIELD_VALUES = ("description", "memo")
BANK_MATCH_ACTION_VALUES = ("post_to_account", "ignore", "flag_for_review")


def upgrade() -> None:
    rule_kind_enum = sa.Enum(*BANK_MATCH_RULE_KIND_VALUES, name="bank_match_rule_kind")
    field_enum = sa.Enum(*BANK_MATCH_FIELD_VALUES, name="bank_match_field")
    action_enum = sa.Enum(*BANK_MATCH_ACTION_VALUES, name="bank_match_action")

    op.create_table(
        "bank_match_rule",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column("match_kind", rule_kind_enum, nullable=False),
        sa.Column("match_field", field_enum, nullable=False),
        sa.Column("match_value", sa.Text(), nullable=False),
        sa.Column("min_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("max_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("action_kind", action_enum, nullable=False),
        sa.Column(
            "debit_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "credit_account_id",
            sa.Uuid(),
            sa.ForeignKey("account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description_template", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
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
        "ix_bank_match_rule_account_active_priority",
        "bank_match_rule",
        ["account_id", "is_active", "priority"],
    )
    op.create_index(
        "ix_bank_match_rule_active_priority",
        "bank_match_rule",
        ["is_active", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_bank_match_rule_active_priority", table_name="bank_match_rule")
    op.drop_index("ix_bank_match_rule_account_active_priority", table_name="bank_match_rule")
    op.drop_table("bank_match_rule")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(*BANK_MATCH_ACTION_VALUES, name="bank_match_action").drop(bind, checkfirst=True)
        sa.Enum(*BANK_MATCH_FIELD_VALUES, name="bank_match_field").drop(bind, checkfirst=True)
        sa.Enum(*BANK_MATCH_RULE_KIND_VALUES, name="bank_match_rule_kind").drop(
            bind, checkfirst=True
        )
