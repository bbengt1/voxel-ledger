"""Pure compound-tax math (Phase 9.5, #157).

5% GST + 8% PST compound on $100 -> $5 + $8.40 = $13.40.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.services import tax as tax_service


def _rate(*, ordinal: int, rate: str, compound: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        ordinal=ordinal,
        rate=Decimal(rate),
        compound_on_previous=compound,
    )


def test_compound_two_rates() -> None:
    rates = [
        _rate(ordinal=0, rate="0.05", compound=False),
        _rate(ordinal=1, rate="0.08", compound=True),
    ]
    out = tax_service.compute_line_tax(line_subtotal=Decimal("100"), rates=rates)
    assert len(out) == 2
    by_id = dict(out)
    assert by_id[rates[0].id] == Decimal("5.000000")
    assert by_id[rates[1].id] == Decimal("8.400000")
    total = sum((amt for _, amt in out), Decimal("0"))
    assert total == Decimal("13.400000")
