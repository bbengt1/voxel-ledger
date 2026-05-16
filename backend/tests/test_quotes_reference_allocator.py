"""Quote reference allocator: distinct QT-YYYY-NNNN under concurrency (Phase 7.2, #110).

Mirrors the sale allocator test (#94). Headline property: N sequential
allocations issue distinct numbers. The DB-level concurrency property
(the upsert holds a row lock) is covered by the dedicated PG allocator
tests under ``tests/test_reference_number_concurrency.py``. This test
guards the QT-prefix wiring + zero-padding format.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from app.services import quotes as quotes_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._quotes_helpers import seed_customer, seed_user

_QT_RE = re.compile(r"^QT-\d{4}-\d{4,}$")


@pytest.mark.asyncio
async def test_sequential_create_issues_distinct_qt_numbers(
    app_session: AsyncSession,
) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)

    numbers: set[str] = set()
    for _ in range(10):
        quote = await quotes_service.create_draft(
            app_session,
            customer_id=customer.id,
            items=[
                {
                    "kind": "manual",
                    "description": "Line",
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
            actor_user_id=user.id,
        )
        await app_session.commit()
        assert _QT_RE.match(quote.quote_number), quote.quote_number
        assert quote.quote_number not in numbers, f"duplicate: {quote.quote_number}"
        numbers.add(quote.quote_number)

    year = datetime.now(UTC).year
    assert all(n.startswith(f"QT-{year}-") for n in numbers)


@pytest.mark.asyncio
async def test_qt_numbers_increment_monotonically(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    customer = await seed_customer(app_session)

    numbers: list[int] = []
    for _ in range(5):
        quote = await quotes_service.create_draft(
            app_session,
            customer_id=customer.id,
            items=[
                {
                    "kind": "manual",
                    "description": "Line",
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
            actor_user_id=user.id,
        )
        await app_session.commit()
        suffix = int(quote.quote_number.rsplit("-", 1)[-1])
        numbers.append(suffix)

    assert numbers == sorted(numbers)
    deltas = [numbers[i + 1] - numbers[i] for i in range(len(numbers) - 1)]
    assert all(d == 1 for d in deltas), numbers
