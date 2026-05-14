"""Replay projection handlers against the event log.

Usage:
    python -m scripts.replay_projections --handler <name> \\
        [--from-position N] [--dry-run]
    python -m scripts.replay_projections --handler all [--dry-run]

``--handler all`` replays every registered handler in handler-name order.
``--from-position`` overrides the stored cursor (pass 0 to replay from
scratch). ``--dry-run`` runs the handlers but rolls back every write — used
to verify a handler doesn't crash before committing to a real rebuild.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make `app` importable when invoked from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend"
if _BACKEND.exists() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Side-effect: imports each projection module so the registry populates.
import app.projections  # noqa: E402, F401
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.projections import registry as projection_registry  # noqa: E402
from app.projections.replay import ReplayResult, replay_handler  # noqa: E402

log = logging.getLogger("replay_projections")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay projection handlers against the event log."
    )
    parser.add_argument(
        "--handler",
        required=True,
        help="Handler name, or 'all' to replay every registered handler.",
    )
    parser.add_argument(
        "--from-position",
        type=int,
        default=None,
        help="Position to start from (default: stored cursor).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run handlers but roll back every transaction.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    engine = make_engine(settings)
    factory = make_session_factory(engine)
    try:
        if args.handler == "all":
            handlers = projection_registry.all_handlers()
            if not handlers:
                log.warning("no projection handlers registered")
                return 0
        else:
            handlers = [projection_registry.get_handler(args.handler)]

        results: list[ReplayResult] = []
        for handler in handlers:
            log.info(
                "replay.start handler=%s from_position=%s dry_run=%s",
                handler.name,
                args.from_position,
                args.dry_run,
            )
            result = await replay_handler(
                handler,
                factory,
                from_position=args.from_position,
                dry_run=args.dry_run,
            )
            results.append(result)

        for r in results:
            log.info(
                "summary handler=%s events_processed=%d last_position=%d dry_run=%s",
                r.handler_name,
                r.events_processed,
                r.last_position,
                r.dry_run,
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
        log.error("replay.failed error=%s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
