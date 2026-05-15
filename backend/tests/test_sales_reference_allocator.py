"""Sale reference allocator: distinct SO-YYYY-NNNN under concurrency (Phase 6.2, #94).

Headline property test: N sequential allocations under a single session
issue distinct numbers. The DB-level concurrency property (the upsert
holds a row lock) is covered by the dedicated PG allocator tests under
``tests/test_reference_number_concurrency.py``. This test guards the
SO-prefix wiring + zero-padding format.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from app.services import sales as sales_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_channel, seed_user

_SO_RE = re.compile(r"^SO-\d{4}-\d{4,}$")


@pytest.mark.asyncio
async def test_sequential_create_issues_distinct_so_numbers(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)

    numbers: set[str] = set()
    for _ in range(10):
        sale = await sales_service.create_draft(
            app_session,
            channel_id=channel.id,
            external_order_id=None,
            customer_name="X",
            customer_email=None,
            occurred_at=datetime.now(UTC),
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
        assert _SO_RE.match(sale.sale_number), sale.sale_number
        assert sale.sale_number not in numbers, f"duplicate: {sale.sale_number}"
        numbers.add(sale.sale_number)

    # Year prefix is the current UTC year.
    year = datetime.now(UTC).year
    assert all(n.startswith(f"SO-{year}-") for n in numbers)


@pytest.mark.asyncio
async def test_so_numbers_increment_monotonically(app_session: AsyncSession) -> None:
    user = await seed_user(app_session)
    channel = await seed_channel(app_session, fee_model="none", fee_percent=None)

    numbers: list[int] = []
    for _ in range(5):
        sale = await sales_service.create_draft(
            app_session,
            channel_id=channel.id,
            external_order_id=None,
            customer_name="X",
            customer_email=None,
            occurred_at=datetime.now(UTC),
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
        suffix = int(sale.sale_number.rsplit("-", 1)[-1])
        numbers.append(suffix)

    assert numbers == sorted(numbers)
    # Each subsequent number is exactly previous + 1.
    deltas = [numbers[i + 1] - numbers[i] for i in range(len(numbers) - 1)]
    assert all(d == 1 for d in deltas), numbers
