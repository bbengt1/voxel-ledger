"""OFX parser tests (Phase 8.9, #136).

Drives ``parse_ofx`` directly with a minimal SGML-style fixture.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from app.services import bank_imports as service

from tests._banking_helpers import sample_ofx_bytes


def test_ofx_minimal_parse() -> None:
    rows = service.parse_ofx(stream=io.BytesIO(sample_ofx_bytes()))
    assert len(rows) == 2
    debit = rows[0]
    assert debit.occurred_on == date(2026, 4, 3)
    assert debit.amount == Decimal("-4.50")
    assert debit.description == "COFFEE SHOP"
    assert debit.memo == "downtown"
    assert debit.fitid == "FIT0001"

    credit = rows[1]
    assert credit.occurred_on == date(2026, 4, 5)
    assert credit.amount == Decimal("2500.00")
    assert credit.fitid == "FIT0002"


def test_ofx_empty_returns_empty_list() -> None:
    rows = service.parse_ofx(stream=io.BytesIO(b"<OFX></OFX>"))
    assert rows == []
