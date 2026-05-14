"""Opt-in development fixtures.

Today Phase 0 ships only `user` and `refresh_token` tables. Owner is seeded by
`scripts/seed_owner.py`; there is nothing else fixture-eligible yet.

This module is the scaffold where Phase 1+ will land illustrative seed data —
materials, supplies, default rates, products with BOMs, a mock printer, and a
sample customer — so contributors have something to look at without manually
filling forms.

Contract for every future fixture added here:

* Idempotent: gate the insert on the destination table being empty (or on a
  natural-key lookup) so re-running over an existing dev DB is a no-op.
* Async session-scoped: `seed_dev_fixtures` receives a `AsyncSession` and is
  responsible for its own commits.
* Quiet on no-op, chatty on insert: print a one-line summary per fixture set.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User


async def seed_dev_fixtures(session: AsyncSession) -> None:
    """Insert dev fixtures. Idempotent — safe to re-run.

    Phase 0 has no fixture-eligible tables beyond `user` (handled by the owner
    seed). This function is a deliberate no-op placeholder. Phase 1+ should
    add `_seed_materials(session)`, `_seed_products(session)`, etc. here.
    """

    user_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    print(f"dev_fixtures: existing users={user_count}")
    print("dev_fixtures: no fixture-eligible tables yet (Phase 0); nothing to insert.")
