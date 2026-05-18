"""ORM model for ``bank_match_rule`` (Phase 8.10, #137).

Operator-defined matchers used by the auto-match worker to classify
``bank_transaction`` rows. A rule fires when the configured ``match_kind``
applied to the ``match_field`` (description/memo) matches ``match_value``
AND the transaction's amount falls within the optional ``min_amount`` /
``max_amount`` bounds.

The action takes one of three shapes:
* ``post_to_account`` — auto-post a balanced JE, link the row.
* ``ignore`` — flip state to ``ignored`` without posting.
* ``flag_for_review`` — leave state, emit event for operator triage.

Per agents.md gotcha #3, the three PG enums are declared with
``SAEnum(..., create_type=False)`` because migration 0048 has already
created them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    true,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BankMatchRuleKind(enum.StrEnum):
    CONTAINS = "contains"
    REGEX = "regex"
    STARTS_WITH = "starts_with"
    EQUALS = "equals"


BANK_MATCH_RULE_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in BankMatchRuleKind)


class BankMatchField(enum.StrEnum):
    DESCRIPTION = "description"
    MEMO = "memo"


BANK_MATCH_FIELD_VALUES: tuple[str, ...] = tuple(m.value for m in BankMatchField)


class BankMatchAction(enum.StrEnum):
    POST_TO_ACCOUNT = "post_to_account"
    IGNORE = "ignore"
    FLAG_FOR_REVIEW = "flag_for_review"


BANK_MATCH_ACTION_VALUES: tuple[str, ...] = tuple(m.value for m in BankMatchAction)


BANK_MATCH_RULE_KIND_ENUM = SAEnum(
    BankMatchRuleKind,
    name="bank_match_rule_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

BANK_MATCH_FIELD_ENUM = SAEnum(
    BankMatchField,
    name="bank_match_field",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

BANK_MATCH_ACTION_ENUM = SAEnum(
    BankMatchAction,
    name="bank_match_action",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


_SA_TRUE = true()


class BankMatchRule(Base):
    __tablename__ = "bank_match_rule"
    __table_args__ = (
        Index(
            "ix_bank_match_rule_account_active_priority",
            "account_id",
            "is_active",
            "priority",
        ),
        Index("ix_bank_match_rule_active_priority", "is_active", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="CASCADE"), nullable=True
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    match_kind: Mapped[BankMatchRuleKind] = mapped_column(BANK_MATCH_RULE_KIND_ENUM, nullable=False)
    match_field: Mapped[BankMatchField] = mapped_column(BANK_MATCH_FIELD_ENUM, nullable=False)
    match_value: Mapped[str] = mapped_column(Text(), nullable=False)
    min_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    action_kind: Mapped[BankMatchAction] = mapped_column(BANK_MATCH_ACTION_ENUM, nullable=False)
    debit_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    credit_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    description_template: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=_SA_TRUE
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
