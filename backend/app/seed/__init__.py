"""Seed helpers.

Canonical:
- `app.seed.owner` — idempotent initial-owner seed. Run automatically by the
  backend entrypoint after migrations; can also be invoked manually as
  `python -m app.seed.owner`. The repo-root `scripts/seed_owner.py` is a
  thin shim for dev/CI workflows that already use that path.
- `app.seed.dev_fixtures` — opt-in dev data, surfaced via `make seed-fixtures`.
"""
