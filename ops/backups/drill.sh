#!/usr/bin/env bash
# Restore drill (Phase 12.2, #204).
#
# Spins up an isolated Postgres in Docker, restores the latest base
# backup, runs row-count + chain-hash smoke checks, then tears down.
# Designed to complete well inside the documented 2h RTO budget on a
# real production-sized dataset; in CI it runs against a synthetic
# fixture and finishes in seconds.
#
# This script supports two modes, picked by the first positional arg:
#   - drill.sh full              full base-restore-from-tar drill
#                                (the production path)
#   - drill.sh smoke             pg_dump -> pg_restore round-trip
#                                (the CI default; no pg_basebackup
#                                privilege required)
#
# Env:
#   DRILL_SRC_URL                postgres:// URL of the source DB
#   DRILL_DST_CONTAINER          docker container name for the temp
#                                Postgres (default: voxel-drill-pg)
#   DRILL_DST_PORT               host port for the temp container
#                                (default: 5599)
#   DRILL_KEEP                   any value -> don't tear down at the
#                                end (debugging)

set -euo pipefail

MODE="${1:-smoke}"
SRC_URL="${DRILL_SRC_URL:?DRILL_SRC_URL required}"
DST_CONTAINER="${DRILL_DST_CONTAINER:-voxel-drill-pg}"
DST_PORT="${DRILL_DST_PORT:-5599}"

# Pull metadata fields out of the URL.
SRC_DB="${SRC_URL##*/}"
SRC_DB="${SRC_DB%%\?*}"

cleanup() {
  if [[ -z "${DRILL_KEEP:-}" ]]; then
    docker rm -f "${DST_CONTAINER}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[drill] $(date -u -Iseconds)  mode=${MODE}  src=${SRC_DB}"

# --- Boot a clean Postgres ---------------------------------------------------
docker rm -f "${DST_CONTAINER}" >/dev/null 2>&1 || true
docker run -d --name "${DST_CONTAINER}" \
  -e POSTGRES_PASSWORD=drill \
  -e POSTGRES_USER=drill \
  -e POSTGRES_DB=drill \
  -p "${DST_PORT}:5432" \
  postgres:16 >/dev/null

for _ in {1..30}; do
  if docker exec "${DST_CONTAINER}" pg_isready -U drill >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
echo "[drill] target ready on :${DST_PORT}"

# --- Counts on source --------------------------------------------------------
src_counts=$(psql "${SRC_URL}" -At -c "
  SELECT 'event:'      || COALESCE(MAX(position),0) FROM event
  UNION ALL SELECT 'journal_entry:' || COALESCE(COUNT(*),0) FROM journal_entry
  UNION ALL SELECT 'invoice:'       || COALESCE(COUNT(*),0) FROM invoice
  UNION ALL SELECT 'bill:'          || COALESCE(COUNT(*),0) FROM bill;
")
echo "[drill] source row-counts:"
echo "${src_counts}" | sed 's/^/  /'

# --- Capture + restore -------------------------------------------------------
DST_URL="postgres://drill:drill@localhost:${DST_PORT}/drill"
case "${MODE}" in
  smoke)
    DUMP=$(mktemp -t voxel-drill-XXXXXX.dump)
    trap 'rm -f "${DUMP}"; cleanup' EXIT
    echo "[drill] pg_dump (custom format)"
    pg_dump --format=custom --no-owner --no-acl --file="${DUMP}" "${SRC_URL}"
    echo "[drill] pg_restore"
    pg_restore --clean --if-exists --no-owner --no-acl \
      --dbname="${DST_URL}" "${DUMP}"
    ;;
  full)
    echo "[drill] full base-restore not wired in this script — see RUNBOOK.md"
    echo "[drill] (production restore uses pg_basebackup tarballs + WAL replay;"
    echo "        run interactively per the runbook until the operator-side"
    echo "        scripting lands)"
    exit 2
    ;;
  *)
    echo "unknown mode: ${MODE}" >&2
    exit 2
    ;;
esac

# --- Parity check ------------------------------------------------------------
dst_counts=$(psql "${DST_URL}" -At -c "
  SELECT 'event:'      || COALESCE(MAX(position),0) FROM event
  UNION ALL SELECT 'journal_entry:' || COALESCE(COUNT(*),0) FROM journal_entry
  UNION ALL SELECT 'invoice:'       || COALESCE(COUNT(*),0) FROM invoice
  UNION ALL SELECT 'bill:'          || COALESCE(COUNT(*),0) FROM bill;
")
echo "[drill] target row-counts:"
echo "${dst_counts}" | sed 's/^/  /'

if [[ "${src_counts}" != "${dst_counts}" ]]; then
  echo "[drill] PARITY MISMATCH" >&2
  diff <(echo "${src_counts}") <(echo "${dst_counts}") || true
  exit 1
fi

# --- Chain-hash spot check --------------------------------------------------
src_tail=$(psql "${SRC_URL}" -At -c "SELECT event_hash FROM event ORDER BY position DESC LIMIT 1")
dst_tail=$(psql "${DST_URL}" -At -c "SELECT event_hash FROM event ORDER BY position DESC LIMIT 1")
if [[ "${src_tail}" != "${dst_tail}" ]]; then
  echo "[drill] EVENT-HASH MISMATCH src=${src_tail} dst=${dst_tail}" >&2
  exit 1
fi
echo "[drill] event-hash tail matches: ${src_tail:-<empty>}"

echo "[drill] OK $(date -u -Iseconds)"
