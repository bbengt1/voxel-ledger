#!/usr/bin/env sh
# Backend production entrypoint.
#
# Runs `alembic upgrade head` before handing off to the main process so the
# container fails fast if migrations are missing or broken. Honors the
# SKIP_MIGRATIONS=1 escape hatch documented in agents.md — use only for
# code-only emergency redeploys when there is no schema delta.

set -eu

if [ "${SKIP_MIGRATIONS:-0}" = "1" ]; then
    echo "[entrypoint] SKIP_MIGRATIONS=1 — skipping alembic upgrade head"
else
    echo "[entrypoint] running alembic upgrade head"
    alembic upgrade head
fi

# Idempotent: app.seed.owner is a no-op if the user table is non-empty.
# Only runs when OWNER_EMAIL and OWNER_PASSWORD are set; SKIP_SEED_OWNER=1
# is an escape hatch for unusual recovery scenarios.
if [ "${SKIP_SEED_OWNER:-0}" = "1" ]; then
    echo "[entrypoint] SKIP_SEED_OWNER=1 — skipping owner seed"
elif [ -n "${OWNER_EMAIL:-}" ] && [ -n "${OWNER_PASSWORD:-}" ]; then
    echo "[entrypoint] running owner seed (idempotent)"
    python -m app.seed.owner
else
    echo "[entrypoint] OWNER_EMAIL/OWNER_PASSWORD not set; skipping owner seed"
fi

echo "[entrypoint] launching: $*"
exec "$@"
