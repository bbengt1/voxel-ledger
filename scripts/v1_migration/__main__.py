"""``python -m scripts.v1_migration`` orchestrator entry-point.

Connects to the v2 DB via the standard app settings + DSN, opens a
session, and runs every registered context in order. Writes a JSON
audit log to ``ops/v1_migration/`` (or the path passed via
``--audit-log-dir``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from app.core import db as db_module
from app.core.settings import Settings
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.v1_migration.framework import run_all

log = logging.getLogger("v1_migration")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="v1_migration")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Read v1 + compute v2 output but rollback every commit.",
    )
    p.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Run only the named contexts (default: all).",
    )
    p.add_argument(
        "--audit-log-dir",
        type=Path,
        default=Path("ops/v1_migration"),
        help="Where to write the per-run JSON audit log.",
    )
    p.add_argument(
        "--v1-fixture",
        type=Path,
        default=None,
        help=(
            "JSON file mapping context-name -> list[row dict]. Test / "
            "rehearsal path; real v1 connections monkey-patch each "
            "context's _read_v1_* function."
        ),
    )
    p.add_argument(
        "--allow-prod",
        action="store_true",
        help="Required to run against a non-localhost v2 DSN.",
    )
    return p.parse_args(argv)


async def _main(argv: list[str]) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    settings = Settings()
    engine = create_async_engine(settings.database_url)
    db_module.set_engine(engine)
    factory = db_module._session_factory
    assert factory is not None

    v1_payload: dict | None = None
    if args.v1_fixture is not None:
        v1_payload = json.loads(args.v1_fixture.read_text())

    async with factory() as session:
        result = await run_all(
            v1_session=v1_payload or {},
            v2_session=session,
            dry_run=args.dry_run,
            only=args.only,
            audit_log_dir=args.audit_log_dir,
            allow_prod=args.allow_prod,
        )

    await db_module.dispose_engine()
    print(result.summary())
    return 0 if result.ok else 1


def main() -> int:  # pragma: no cover - thin wrapper
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
