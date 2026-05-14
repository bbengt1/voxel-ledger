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

echo "[entrypoint] launching: $*"
exec "$@"
