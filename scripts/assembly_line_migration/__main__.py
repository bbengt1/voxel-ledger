"""``python -m scripts.assembly_line_migration`` entry-point (epic #267,
Phase 7a).

Dry-run is the **default**: it reads the live DB, computes the full plan
(derive parts → product BOMs → re-point jobs) and prints counts + the
manual-review list **without writing**. Pass ``--commit`` to apply (one
atomic transaction). ``--reverse`` runs the scripted inverse.

    python -m scripts.assembly_line_migration              # dry-run plan
    python -m scripts.assembly_line_migration --commit     # apply
    python -m scripts.assembly_line_migration --only derive_parts
    python -m scripts.assembly_line_migration --reverse --commit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.core import db as db_module
from app.core.settings import Settings
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.assembly_line_migration.framework import run_all
from scripts.assembly_line_migration.reverse import reverse_all

log = logging.getLogger("assembly_line_migration")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="assembly_line_migration")
    p.add_argument(
        "--commit",
        action="store_true",
        help="Apply changes. Without this, runs a read-only dry-run (default).",
    )
    p.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Run only the named steps (derive_parts product_boms repoint_jobs).",
    )
    p.add_argument(
        "--reverse",
        action="store_true",
        help="Run the scripted inverse (undo a prior commit) instead of the backfill.",
    )
    p.add_argument(
        "--report-dir",
        type=Path,
        default=Path("ops/assembly_line_migration"),
        help="Where to write the per-run JSON report.",
    )
    return p.parse_args(argv)


async def _main(argv: list[str]) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    dry_run = not args.commit

    settings = Settings()
    engine = create_async_engine(settings.database_url)
    db_module.set_engine(engine)
    factory = db_module._session_factory
    assert factory is not None

    async with factory() as session:
        if args.reverse:
            rev = await reverse_all(session=session, dry_run=dry_run)
            print(rev.summary())
            await db_module.dispose_engine()
            return 0 if rev.ok else 1

        result = await run_all(
            session=session,
            dry_run=dry_run,
            only=args.only,
            report_dir=args.report_dir,
        )

    await db_module.dispose_engine()
    print(result.summary())
    return 0 if result.ok else 1


def main() -> int:  # pragma: no cover - thin wrapper
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
