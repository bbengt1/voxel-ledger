"""Pure flat-tax math: both rates flat on subtotal (Phase 9.5, #157)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.services import tax as tax_service


def _rate(*, ordinal: int, rate: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        ordinal=ordinal,
        rate=Decimal(rate),
        compound_on_previous=False,
    )


def test_flat_two_rates() -> None:
    rates = [
        _rate(ordinal=0, rate="0.05"),
        _rate(ordinal=1, rate="0.08"),
    ]
    out = tax_service.compute_line_tax(line_subtotal=Decimal("100"), rates=rates)
    by_id = dict(out)
    assert by_id[rates[0].id] == Decimal("5.000000")
    assert by_id[rates[1].id] == Decimal("8.000000")
    total = sum((amt for _, amt in out), Decimal("0"))
    assert total == Decimal("13.000000")
