"""Run dev fixtures against the current database.

Idempotent. Reads settings from the same env as the backend (DATABASE_URL,
etc.). Intended to be invoked via `make seed-fixtures` after the stack is up
and migrations have run.

Run with either:
    python -m scripts.seed_dev
    python scripts/seed_dev.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend"
if _BACKEND.exists() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.seed.dev_fixtures import seed_dev_fixtures  # noqa: E402


async def run() -> int:
    settings = load_settings()
    engine = make_engine(settings)
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            await seed_dev_fixtures(session)
            await session.commit()
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
