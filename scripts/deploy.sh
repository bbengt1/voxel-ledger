#!/usr/bin/env bash
# Voxel Ledger deploy script.
#
# Pulls the latest `main`, runs Alembic migrations, rebuilds the prod compose
# stack, and verifies `/health`. Designed to run from `/srv/3d-print-sales/repo`
# on `web01`, but works against any host where the prod stack is the right
# target (the n8n workflow at ops/n8n/web01-deploy.json calls this).
#
# Override knobs (env vars):
#   SKIP_MIGRATIONS=1   skip `alembic upgrade head` (code-only emergencies)
#   HEALTH_URL          override the health-check URL
#                       (default: http://127.0.0.1/health)
#   HEALTH_TIMEOUT      seconds to wait for /health to return 200
#                       (default: 60)
#   COMPOSE             override the compose wrapper invocation
#                       (default: scripts/web01-compose.sh)
#
# Exit codes are non-zero on the first failing step, with a clear
# "FAILED at step N" message so the n8n workflow surfaces it to the operator.

set -euo pipefail

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1/health}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
COMPOSE="${COMPOSE:-scripts/web01-compose.sh}"

CURRENT_STEP="(init)"

log() {
    printf '[deploy] %s\n' "$*"
}

warn() {
    printf '[deploy] WARNING: %s\n' "$*" >&2
}

on_error() {
    local exit_code=$?
    printf '[deploy] FAILED at step %s (exit %d)\n' "$CURRENT_STEP" "$exit_code" >&2
    exit "$exit_code"
}

trap on_error ERR

step() {
    CURRENT_STEP="$1"
    log "step $1: $2"
}

# --- 1. Validate cwd is a repo checkout root. --------------------------------
step 1 "validate repo checkout"
if [ ! -d .git ] || [ ! -f docker-compose.prod.yml ] || [ ! -x scripts/web01-compose.sh ]; then
    warn "deploy.sh must be run from the repo checkout root"
    warn "  cwd: $(pwd)"
    warn "  expected: a checkout containing docker-compose.prod.yml and scripts/web01-compose.sh"
    exit 1
fi

# --- 2. Fast-forward main from origin. ---------------------------------------
step 2 "git fetch + fast-forward main"
git fetch origin
# `git checkout main` is a no-op if we're already on main, but covers operators
# who land on a detached HEAD after a rollback.
git checkout main
git pull --ff-only origin main

# --- 3. Print the deploying commit. ------------------------------------------
step 3 "report target commit"
DEPLOY_SHA="$(git rev-parse HEAD)"
DEPLOY_SHORT="$(git rev-parse --short HEAD)"
log "deploying ${DEPLOY_SHORT} (${DEPLOY_SHA})"
git --no-pager log -1 --pretty=format:'        %s%n        %an <%ae> %ad' --date=iso

# --- 4. Migrations (mandatory unless SKIP_MIGRATIONS=1). ---------------------
step 4 "alembic upgrade head"
if [ "${SKIP_MIGRATIONS:-}" = "1" ]; then
    warn "================================================================"
    warn "SKIP_MIGRATIONS=1 set — skipping alembic upgrade head."
    warn "This is only safe for CODE-ONLY emergency redeploys."
    warn "If this deploy includes a schema change, the backend WILL crash"
    warn "at startup. (See v1 incident 2026-05-09, PR #271/#239.)"
    warn "================================================================"
else
    "${COMPOSE}" run --rm backend alembic upgrade head
fi

# --- 5. Rebuild and rotate the stack. ----------------------------------------
step 5 "compose up -d --build"
"${COMPOSE}" up -d --build

# --- 6. Restart nginx so it re-resolves upstreams. ---------------------------
# When ``up -d --build`` recreates the backend/frontend containers they get
# fresh IPs, but the long-running nginx container caches the old ones in its
# resolver and serves 502s until restarted. A restart forces re-resolution.
# Tolerated as non-fatal: if nginx isn't part of this stack the health poll
# below is the real gate.
step 6 "restart nginx (clear stale upstreams)"
"${COMPOSE}" restart nginx || warn "nginx restart skipped/failed; continuing to health check"

# --- 7. Poll /health. --------------------------------------------------------
step 7 "wait for ${HEALTH_URL}"
deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
attempt=0
until curl -fsS -o /dev/null "${HEALTH_URL}"; do
    attempt=$(( attempt + 1 ))
    if [ "$(date +%s)" -ge "${deadline}" ]; then
        warn "health check did not succeed within ${HEALTH_TIMEOUT}s (attempt ${attempt})"
        warn "  tail backend logs with: ${COMPOSE} logs --tail=200 backend"
        exit 1
    fi
    sleep 2
done
log "health check passed after ${attempt} attempt(s)"

# --- 8. Final state snapshot. ------------------------------------------------
step 8 "compose ps"
"${COMPOSE}" ps

CURRENT_STEP="(done)"
log "deploy succeeded: ${DEPLOY_SHORT}"
