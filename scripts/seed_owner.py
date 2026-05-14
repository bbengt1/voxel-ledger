"""Seed the initial owner user from env (OWNER_EMAIL / OWNER_PASSWORD).

Idempotent: if the user table is non-empty, prints a notice and exits 0.

Run with either:
    python -m scripts.seed_owner
    python scripts/seed_owner.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as `python scripts/seed_owner.py` from repo root by ensuring
# `backend/` is importable. `python -m scripts.seed_owner` works regardless.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend"
if _BACKEND.exists() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.models.auth import Role, User  # noqa: E402
from app.services.auth import create_user  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


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
            count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
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
