"""ORM models for the ``banking`` bounded context (Phase 8.9, #136).

* :class:`BankImportMapping` — operator-defined CSV column maps. OFX
  files are structured and don't need a mapping.
* :class:`BankImportRun` — a single import action's summary.
* :class:`BankTransaction` — the parsed rows. Dedup is enforced by a
  unique constraint on ``(account_id, external_hash)``.

All three PG enums are auto-created by the 0047 migration. Per agents.md
gotcha #3, the ORM declares them with ``SAEnum(..., create_type=False)``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class BankImportFileKind(enum.StrEnum):
    CSV = "csv"
    OFX = "ofx"


BANK_IMPORT_FILE_KIND_VALUES: tuple[str, ...] = tuple(m.value for m in BankImportFileKind)


class BankTransactionState(enum.StrEnum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"
    IGNORED = "ignored"
    CLEARED = "cleared"


BANK_TRANSACTION_STATE_VALUES: tuple[str, ...] = tuple(m.value for m in BankTransactionState)


class BankAmountSign(enum.StrEnum):
    SIGNED_AMOUNT = "signed_amount"
    DEBIT_CREDIT_COLUMNS = "debit_credit_columns"
    INFLOW_OUTFLOW = "inflow_outflow"


BANK_AMOUNT_SIGN_VALUES: tuple[str, ...] = tuple(m.value for m in BankAmountSign)


BANK_IMPORT_FILE_KIND_ENUM = SAEnum(
    BankImportFileKind,
    name="bank_import_file_kind",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

BANK_TRANSACTION_STATE_ENUM = SAEnum(
    BankTransactionState,
    name="bank_transaction_state",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)

BANK_AMOUNT_SIGN_ENUM = SAEnum(
    BankAmountSign,
    name="bank_amount_sign",
    values_callable=lambda enum_cls: [m.value for m in enum_cls],
    create_type=False,
)


_SA_TRUE = true()


class BankImportMapping(Base):
    __tablename__ = "bank_import_mapping"
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_bank_import_mapping_account_name"),
        Index("ix_bank_import_mapping_account_id", "account_id"),
        Index("ix_bank_import_mapping_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    file_kind: Mapped[BankImportFileKind] = mapped_column(
        BANK_IMPORT_FILE_KIND_ENUM, nullable=False
    )
    column_map: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    date_format: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delimiter: Mapped[str] = mapped_column(
        String(4), nullable=False, default=",", server_default=","
    )
    has_header: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=_SA_TRUE
    )
    encoding: Mapped[str] = mapped_column(
        String(32), nullable=False, default="utf-8", server_default="utf-8"
    )
    amount_sign: Mapped[BankAmountSign] = mapped_column(BANK_AMOUNT_SIGN_ENUM, nullable=False)
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


class BankImportRun(Base):
    __tablename__ = "bank_import_run"
    __table_args__ = (
        Index(
            "ix_bank_import_run_account_id_imported_at",
            "account_id",
            "imported_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    mapping_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bank_import_mapping.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    imported_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    inserted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)


class BankTransaction(Base):
    __tablename__ = "bank_transaction"
    __table_args__ = (
        UniqueConstraint("account_id", "external_hash", name="uq_bank_transaction_account_hash"),
        Index("ix_bank_transaction_account_state", "account_id", "state"),
        Index("ix_bank_transaction_account_occurred_on", "account_id", "occurred_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    import_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bank_import_run.id", ondelete="SET NULL"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    occurred_on: Mapped[date] = mapped_column(Date(), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False, default="", server_default="")
    memo: Mapped[str | None] = mapped_column(Text(), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    running_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    fitid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[BankTransactionState] = mapped_column(
        BANK_TRANSACTION_STATE_ENUM,
        nullable=False,
        default=BankTransactionState.UNMATCHED,
        server_default="unmatched",
    )
    matched_journal_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("journal_line.id", ondelete="SET NULL"), nullable=True
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

    import_run: Mapped[BankImportRun | None] = relationship("BankImportRun")


# Silence "imported but unused" for the false helper that other models cross-reference.
_ = false
