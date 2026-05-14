"""Rebuild a single projection from the event log.

Usage:
    python -m scripts.rebuild_projection --handler <name> --yes-really
    python -m scripts.rebuild_projection --handler <name>   # dry preview

Truncates the handler's declared read-model tables, deletes its
``projection_cursor`` row, then replays the handler from position 0.

The ``--yes-really`` flag is required to actually perform the rebuild.
Without it, the script prints what it would do and exits 0 — useful for
double-checking before running destructively.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend"
if _BACKEND.exists() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import app.projections  # noqa: E402, F401
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.projections import registry as projection_registry  # noqa: E402
from app.projections.replay import (  # noqa: E402
    delete_cursor,
    replay_handler,
    truncate_read_model_tables,
)

log = logging.getLogger("rebuild_projection")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild a projection by truncating its read-model "
        "tables and replaying from position 0."
    )
    parser.add_argument("--handler", required=True, help="Handler name.")
    parser.add_argument(
        "--yes-really",
        action="store_true",
        help="Required to actually truncate and replay. Without it, the "
        "script prints what it would do and exits 0.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    engine = make_engine(settings)
    factory = make_session_factory(engine)
    try:
        handler = projection_registry.get_handler(args.handler)

        if not args.yes_really:
            log.warning(
                "DRY PREVIEW (no --yes-really). Would truncate tables=%s "
                "and replay handler=%s from position 0.",
                list(handler.read_model_tables),
                handler.name,
            )
            return 0

        log.info(
            "rebuild.start handler=%s tables=%s",
            handler.name,
            list(handler.read_model_tables),
        )
        async with factory() as session:
            await truncate_read_model_tables(session, handler.read_model_tables)
            await delete_cursor(session, handler.name)
            await session.commit()

        result = await replay_handler(handler, factory, from_position=0)
        log.info(
            "rebuild.done handler=%s events_processed=%d last_position=%d",
            result.handler_name,
            result.events_processed,
            result.last_position,
        )
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # pragma: no cover - top-level guard
        log.error("rebuild.failed error=%s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
