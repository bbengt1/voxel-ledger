"""Phase 8.5 (#132): compute_next_issue_at pure cadence math (AP mirror)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.recurring_bill import RecurringBillCadenceKind
from app.services.recurring_bills import compute_next_issue_at


@pytest.mark.parametrize(
    "kind,interval,expected_month,expected_day",
    [
        (RecurringBillCadenceKind.DAILY, 1, 1, 2),
        (RecurringBillCadenceKind.DAILY, 7, 1, 8),
        (RecurringBillCadenceKind.WEEKLY, 1, 1, 8),
        (RecurringBillCadenceKind.WEEKLY, 2, 1, 15),
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
        cadence_kind=RecurringBillCadenceKind.MONTHLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2025, 2, 15, 12, 0, tzinfo=UTC)


def test_cadence_monthly_jan_31_falls_back_to_feb_end() -> None:
    base = datetime(2025, 1, 31, 9, 30, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringBillCadenceKind.MONTHLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2025, 2, 28, 9, 30, tzinfo=UTC)


def test_cadence_monthly_jan_31_leap_year_feb_29() -> None:
    base = datetime(2024, 1, 31, 9, 30, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringBillCadenceKind.MONTHLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2024, 2, 29, 9, 30, tzinfo=UTC)


def test_cadence_quarterly() -> None:
    base = datetime(2025, 1, 15, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringBillCadenceKind.QUARTERLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2025, 4, 15, tzinfo=UTC)


def test_cadence_yearly() -> None:
    base = datetime(2025, 2, 28, tzinfo=UTC)
    nxt = compute_next_issue_at(
        from_dt=base,
        cadence_kind=RecurringBillCadenceKind.YEARLY,
        cadence_interval=1,
    )
    assert nxt == datetime(2026, 2, 28, tzinfo=UTC)


def test_cadence_accepts_string_kind() -> None:
    base = datetime(2025, 6, 1, tzinfo=UTC)
    nxt = compute_next_issue_at(from_dt=base, cadence_kind="monthly", cadence_interval=3)
    assert nxt == datetime(2025, 9, 1, tzinfo=UTC)
