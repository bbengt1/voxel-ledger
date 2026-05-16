"""Phase 7.5 (#113): compute_next_issue_at pure cadence math."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.recurring_invoice import RecurringCadenceKind
from app.services.recurring_invoices import compute_next_issue_at


@pytest.mark.parametrize(
    "kind,interval,expected_month,expected_day",
    [
        (RecurringCadenceKind.DAILY, 1, 1, 2),
        (RecurringCadenceKind.DAILY, 7, 1, 8),
        (RecurringCadenceKind.WEEKLY, 1, 1, 8),
        (RecurringCadenceKind.WEEKLY, 2, 1, 15),
    ],
)
def test_cadence_daily_weekly(kind, interval, expected_month, expected_day) -> None:
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    nxt = compute_next_issue_at(from_dt=base, cadence_kind=kind, cadence_interval=interval)
    assert nxt.month == expected_month
    assert nxt.day == expected_day
    assert nxt.year == 2025


def test_cadence_monthly_simple() -> None:
    base = datetime(2025, 1, 15, 12, 0, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringCadenceKind.MONTHLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2025, 2, 15, 12, 0, tzinfo=UTC)


def test_cadence_monthly_jan_31_falls_back_to_feb_end() -> None:
    """Jan 31 + 1 month must be Feb 28 (non-leap) — not roll over."""
    base = datetime(2025, 1, 31, 9, 30, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringCadenceKind.MONTHLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2025, 2, 28, 9, 30, tzinfo=UTC)


def test_cadence_monthly_jan_31_leap_year_feb_29() -> None:
    base = datetime(2024, 1, 31, 9, 30, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringCadenceKind.MONTHLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2024, 2, 29, 9, 30, tzinfo=UTC)


def test_cadence_monthly_interval_2() -> None:
    base = datetime(2025, 1, 31, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringCadenceKind.MONTHLY,
        cadence_interval=2,
    )
    # Jan 31 + 2 months = Mar 31
    assert nxt == datetime(2025, 3, 31, tzinfo=UTC)


def test_cadence_quarterly() -> None:
    base = datetime(2025, 1, 15, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringCadenceKind.QUARTERLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2025, 4, 15, tzinfo=UTC)


def test_cadence_yearly() -> None:
    base = datetime(2025, 2, 28, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringCadenceKind.YEARLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2026, 2, 28, tzinfo=UTC)


def test_cadence_yearly_leap_feb_29_to_feb_28() -> None:
    base = datetime(2024, 2, 29, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringCadenceKind.YEARLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2025, 2, 28, tzinfo=UTC)


def test_cadence_accepts_string_kind() -> None:
    base = datetime(2025, 6, 1, tzinfo=UTC)
    nxt = compute_next_issue_at(from_dt=base, cadence_kind="monthly", cadence_interval=3)
    assert nxt == datetime(2025, 9, 1, tzinfo=UTC)
