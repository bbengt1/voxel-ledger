"""Etsy CSV parser unit test (Phase 9.8, #160)."""

from __future__ import annotations

import io
from decimal import Decimal

from app.services.settlement_imports import parse_etsy_csv

from tests._settlement_helpers import sample_etsy_csv_bytes


def test_parse_etsy_csv_returns_5_rows_with_normalized_kinds() -> None:
    raw = sample_etsy_csv_bytes()
    rows = parse_etsy_csv(stream=io.StringIO(raw.decode("utf-8")))
    assert len(rows) == 5

    kinds = [r.line_kind for r in rows]
    assert kinds == ["sale", "fee", "refund", "adjustment", "payout"]

    sale = rows[0]
    assert sale.external_order_id == "ETSY-1001"
    assert sale.external_txn_id == "TX-1001"
    assert sale.amount == Decimal("20.00")
    assert sale.description == "Tiny Voxel Print"

    fee = rows[1]
    assert fee.amount == Decimal("-1.30")

    refund = rows[2]
    assert refund.amount == Decimal("-5.00")
