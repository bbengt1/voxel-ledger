"""Direct CSV parser tests against three real-world variants (Phase 8.9, #136).

Drives ``parse_csv`` directly with synthesized fixtures (no DB needed).
"""

from __future__ import annotations

import io
import uuid
from decimal import Decimal

import pytest
from app.models.bank import (
    BankAmountSign,
    BankImportFileKind,
    BankImportMapping,
)
from app.services import bank_imports as service

from tests._banking_helpers import (
    sample_csv_debit_credit,
    sample_csv_inflow_outflow,
    sample_csv_signed_amount,
)


def _mapping(
    *,
    column_map: dict,
    amount_sign: BankAmountSign,
    date_format: str | None = None,
) -> BankImportMapping:
    return BankImportMapping(
        id=uuid.uuid4(),
        name="m",
        account_id=uuid.uuid4(),
        file_kind=BankImportFileKind.CSV,
        column_map=column_map,
        date_format=date_format,
        delimiter=",",
        has_header=True,
        encoding="utf-8",
        amount_sign=amount_sign,
        is_active=True,
        created_by_user_id=uuid.uuid4(),
    )


def test_signed_amount_csv() -> None:
    m = _mapping(
        column_map={
            "date": "Date",
            "description": "Description",
            "amount": "Amount",
            "balance": "Balance",
        },
        amount_sign=BankAmountSign.SIGNED_AMOUNT,
        date_format="%Y-%m-%d",
    )
    rows = service.parse_csv(
        stream=io.StringIO(sample_csv_signed_amount().decode("utf-8")),
        mapping=m,
    )
    assert len(rows) == 4
    assert rows[2].description == "DEPOSIT PAYROLL"
    assert rows[2].amount == Decimal("2500.00")
    assert rows[3].amount == Decimal("-1200.00")
    assert rows[0].running_balance == Decimal("1000.00")


def test_debit_credit_columns_csv() -> None:
    m = _mapping(
        column_map={
            "date": "Date",
            "description": "Description",
            "debit": "Debit",
            "credit": "Credit",
        },
        amount_sign=BankAmountSign.DEBIT_CREDIT_COLUMNS,
        date_format="%m/%d/%Y",
    )
    rows = service.parse_csv(
        stream=io.StringIO(sample_csv_debit_credit().decode("utf-8")),
        mapping=m,
    )
    assert len(rows) == 4
    # GROCERY: 52.10 debit → -52.10
    assert rows[1].amount == Decimal("-52.10")
    # REFUND: 18.99 credit → +18.99
    assert rows[2].amount == Decimal("18.99")
    assert rows[3].amount == Decimal("-135.00")


def test_inflow_outflow_csv() -> None:
    m = _mapping(
        column_map={
            "date": "Date",
            "description": "Description",
            "inflow": "Inflow",
            "outflow": "Outflow",
        },
        amount_sign=BankAmountSign.INFLOW_OUTFLOW,
        date_format="%Y-%m-%d",
    )
    rows = service.parse_csv(
        stream=io.StringIO(sample_csv_inflow_outflow().decode("utf-8")),
        mapping=m,
    )
    assert len(rows) == 3
    assert rows[0].amount == Decimal("-42.50")
    assert rows[1].amount == Decimal("500.00")
    assert rows[2].amount == Decimal("-28.75")


def test_csv_requires_date_in_column_map() -> None:
    m = _mapping(
        column_map={"description": "Description", "amount": "Amount"},
        amount_sign=BankAmountSign.SIGNED_AMOUNT,
    )
    with pytest.raises(ValueError, match="date"):
        service.parse_csv(
            stream=io.StringIO("foo,bar\n1,2\n"),
            mapping=m,
        )
