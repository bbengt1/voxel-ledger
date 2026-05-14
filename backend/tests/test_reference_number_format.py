"""Pure-function tests for ``format_reference`` / ``parse_reference``.

No DB. Covers the round-trip property, padding expansion, and the bad-
input behavior of the parser.
"""

from __future__ import annotations

import pytest
from app.services.reference_number import (
    DEFAULT_PADDING,
    format_reference,
    parse_reference,
)


@pytest.mark.parametrize(
    "prefix,year,value,expected",
    [
        ("S", 2026, 1, "S-2026-0001"),
        ("S", 2026, 42, "S-2026-0042"),
        ("INV", 2026, 1, "INV-2026-0001"),
        ("BILL", 9999, 9999, "BILL-9999-9999"),
        # Padding expansion — value larger than default padding.
        ("S", 2026, 10000, "S-2026-10000"),
        ("Q", 2027, 123456, "Q-2027-123456"),
    ],
)
def test_format_reference_examples(prefix: str, year: int, value: int, expected: str) -> None:
    assert format_reference(prefix, year, value) == expected


@pytest.mark.parametrize(
    "prefix,year,value",
    [
        ("S", 2026, 1),
        ("INV", 2026, 9999),
        ("Q", 2027, 10000),
        ("BILL", 9999, 123456),
        ("X", 2026, 1),
    ],
)
def test_format_then_parse_roundtrip(prefix: str, year: int, value: int) -> None:
    formatted = format_reference(prefix, year, value, DEFAULT_PADDING)
    assert parse_reference(formatted) == (prefix, year, value)


def test_format_respects_custom_padding() -> None:
    assert format_reference("S", 2026, 1, padding=6) == "S-2026-000001"


def test_format_expands_when_value_exceeds_padding() -> None:
    """Padding is a minimum width, never a maximum. The suffix grows
    rather than truncating — collisions would be forever."""
    assert format_reference("S", 2026, 10_000, padding=4) == "S-2026-10000"
    assert format_reference("S", 2026, 1_234_567, padding=4) == "S-2026-1234567"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "S",
        "S-2026",
        "S-2026-",
        "s-2026-0001",  # lowercase prefix
        "S-26-0001",  # 2-digit year
        "S-2026-ABCD",
        "S 2026 0001",
        "S-2026-0001-extra",
        "-2026-0001",
    ],
)
def test_parse_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_reference(bad)
