"""Idempotent initial-owner seed.

Reads `OWNER_EMAIL` / `OWNER_PASSWORD` from settings and, if the `user` table
is empty, inserts a single OWNER-role user with that email + a hashed
password. If any user already exists, exits 0 with a notice — this is what
makes the seed safe to run on every deploy.

Run inside the backend container:

    python -m app.seed.owner

A repo-root shim at `scripts/seed_owner.py` re-exports `seed()` / `main()`
so existing dev and CI workflows (`python -m scripts.seed_owner`,
`make seed`) keep working without change.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from app.core.db import make_engine, make_session_factory
from app.core.settings import load_settings
from app.models.auth import Role, User
from app.services.auth import create_user


async def seed() -> int:
    settings = load_settings()
    if not settings.owner_email or not settings.owner_password:
        print(
            "OWNER_EMAIL and OWNER_PASSWORD must be set in the environment.",
            file=sys.stderr,
        )
        return 1

    engine = make_engine(settings)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            count = (
                await session.execute(select(func.count()).select_from(User))
            ).scalar_one()
            if count and count > 0:
                print("owner already exists (user table non-empty); nothing to do.")
                return 0

            await create_user(
                session,
                email=settings.owner_email,
                password=settings.owner_password,
                full_name="Owner",
                role=Role.OWNER,
                bcrypt_rounds=settings.bcrypt_rounds,
            )
            await session.commit()
            print(f"owner seeded: {settings.owner_email}")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(seed())


if __name__ == "__main__":
    raise SystemExit(main())
