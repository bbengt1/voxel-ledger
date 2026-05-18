"""Generic CSV parser with custom column_map (Phase 9.8, #160)."""

from __future__ import annotations

import io
from decimal import Decimal

from app.services.settlement_imports import parse_generic_csv

from tests._settlement_helpers import sample_generic_csv_bytes


def test_parse_generic_csv_with_custom_column_names() -> None:
    raw = sample_generic_csv_bytes(
        rows=[
            {
                "TransactedOn": "2026-04-01",
                "Kind": "sale",
                "OrderRef": "SHOP-100",
                "TxnRef": "TX-100",
                "Note": "T-shirt",
                "Money": "29.99",
            },
            {
                "TransactedOn": "2026-04-02",
                "Kind": "fee",
                "OrderRef": "SHOP-100",
                "TxnRef": "TX-100-FEE",
                "Note": "platform fee",
                "Money": "-2.50",
            },
        ],
        header=["TransactedOn", "Kind", "OrderRef", "TxnRef", "Note", "Money"],
    )
    rows = parse_generic_csv(
        stream=io.StringIO(raw.decode("utf-8")),
        column_map={
            "date": "TransactedOn",
            "amount": "Money",
            "line_kind": "Kind",
            "description": "Note",
            "external_order_id": "OrderRef",
            "external_txn_id": "TxnRef",
        },
    )
    assert len(rows) == 2
    assert rows[0].line_kind == "sale"
    assert rows[0].amount == Decimal("29.99")
    assert rows[0].external_order_id == "SHOP-100"
    assert rows[1].line_kind == "fee"
    assert rows[1].amount == Decimal("-2.50")
