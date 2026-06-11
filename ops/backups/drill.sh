#!/usr/bin/env bash
# Restore drill (Phase 12.2, #204; full mode lands in #212).
#
# Two modes, picked by the first positional arg:
#
#   drill.sh smoke   pg_dump -> pg_restore round-trip against an
#                    existing source DB. Tests the schema + data
#                    payload (real app schema, real rows). Used by
#                    the per-PR CI gate. Requires DRILL_SRC_URL.
#
#   drill.sh full    End-to-end WAL-archive + base-backup + PITR
#                    replay. Self-contained: launches its own
#                    primary + target Postgres containers, writes
#                    synthetic data, takes a base backup, writes
#                    *more* data, captures a recovery-target
#                    timestamp, then restores the base on a target
#                    and asserts the post-base data replayed in.
#                    Validates the OPS MECHANICS (archive_command,
#                    restore_command, recovery_target_time) without
#                    needing the app schema or alembic.
#
# Env (smoke):
#   DRILL_SRC_URL                postgres:// URL of the source DB
#   DRILL_DST_CONTAINER          docker container name for the temp
#                                Postgres (default: voxel-drill-pg)
#   DRILL_DST_PORT               host port for the temp container
#                                (default: 5599)
# Env (full):
#   DRILL_PRIMARY_CONTAINER      default: voxel-drill-primary
#   DRILL_TARGET_CONTAINER       default: voxel-drill-target
#   DRILL_FULL_VOLUME            named docker volume for the shared
#                                /backup tree (default: voxel-drill-vol)
#
# Shared env:
#   DRILL_KEEP                   any value -> don't tear down at the
#                                end (debugging)

set -euo pipefail

MODE="${1:-smoke}"
SRC_URL="${DRILL_SRC_URL:-}"
DST_CONTAINER="${DRILL_DST_CONTAINER:-voxel-drill-pg}"
DST_PORT="${DRILL_DST_PORT:-5599}"
PRIMARY="${DRILL_PRIMARY_CONTAINER:-voxel-drill-primary}"
TARGET="${DRILL_TARGET_CONTAINER:-voxel-drill-target}"
SHARED_VOL="${DRILL_FULL_VOLUME:-voxel-drill-vol}"

case "${MODE}" in
  smoke)
    if [[ -z "${SRC_URL}" ]]; then
      echo "DRILL_SRC_URL is required for smoke mode" >&2
      exit 2
    fi
    ;;
  full) ;;
  *)
    echo "unknown mode: ${MODE} (smoke|full)" >&2
    exit 2
    ;;
esac

DRILL_KEEP="${DRILL_KEEP:-}"

cleanup() {
  if [[ -z "${DRILL_KEEP}" ]]; then
    docker rm -f "${DST_CONTAINER}" "${PRIMARY}" "${TARGET}" >/dev/null 2>&1 || true
    docker volume rm "${SHARED_VOL}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_pg() {
  local container="$1"
  local user="${2:-drill}"
  for _ in {1..40}; do
    if docker exec "${container}" pg_isready -U "${user}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "[drill] ${container} never became ready" >&2
  docker logs --tail=80 "${container}" >&2 || true
  return 1
}

# ---------------------------------------------------------------------------
# Postgres client tools (smoke mode): prefer host binaries, fall back to the
# postgres:16 image when the host has none (CI runners ship docker but not
# the client package). --network host keeps the localhost URLs working; the
# drill temp dir is bind-mounted so pg_dump and pg_restore share the dump
# file with the host.
# ---------------------------------------------------------------------------
CLIENT_IMAGE="${DRILL_CLIENT_IMAGE:-postgres:16}"
DRILL_TMPDIR=""

pg_client() {
  local tool="$1"; shift
  if command -v "${tool}" >/dev/null 2>&1; then
    "${tool}" "$@"
  else
    docker run --rm --network host \
      ${DRILL_TMPDIR:+-v "${DRILL_TMPDIR}:${DRILL_TMPDIR}"} \
      "${CLIENT_IMAGE}" "${tool}" "$@"
  fi
}

# ---------------------------------------------------------------------------
# smoke mode
# ---------------------------------------------------------------------------

run_smoke() {
  local src_db
  src_db="${SRC_URL##*/}"; src_db="${src_db%%\?*}"
  echo "[drill] $(date -u -Iseconds)  mode=smoke  src=${src_db}"

  docker rm -f "${DST_CONTAINER}" >/dev/null 2>&1 || true
  docker run -d --name "${DST_CONTAINER}" \
    -e POSTGRES_PASSWORD=drill -e POSTGRES_USER=drill -e POSTGRES_DB=drill \
    -p "${DST_PORT}:5432" postgres:16 >/dev/null
  wait_pg "${DST_CONTAINER}"
  echo "[drill] target ready on :${DST_PORT}"

  local src_counts
  src_counts=$(pg_client psql "${SRC_URL}" -At -c "
    SELECT 'event:'      || COALESCE(MAX(position),0) FROM event
    UNION ALL SELECT 'journal_entry:' || COALESCE(COUNT(*),0) FROM journal_entry
    UNION ALL SELECT 'invoice:'       || COALESCE(COUNT(*),0) FROM invoice
    UNION ALL SELECT 'bill:'          || COALESCE(COUNT(*),0) FROM bill;
  ")
  echo "[drill] source row-counts:"
  echo "${src_counts}" | sed 's/^/  /'

  local dst_url="postgres://drill:drill@localhost:${DST_PORT}/drill"
  DRILL_TMPDIR=$(mktemp -d -t voxel-drill-XXXXXX)
  local dump="${DRILL_TMPDIR}/payload.dump"
  trap 'rm -rf "${DRILL_TMPDIR}"; cleanup' EXIT
  echo "[drill] pg_dump (custom format)"
  pg_client pg_dump --format=custom --no-owner --no-acl --file="${dump}" "${SRC_URL}"
  echo "[drill] pg_restore"
  pg_client pg_restore --clean --if-exists --no-owner --no-acl \
    --dbname="${dst_url}" "${dump}"

  local dst_counts
  dst_counts=$(pg_client psql "${dst_url}" -At -c "
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

  local src_tail dst_tail
  src_tail=$(pg_client psql "${SRC_URL}" -At -c \
    "SELECT event_hash FROM event ORDER BY position DESC LIMIT 1")
  dst_tail=$(pg_client psql "${dst_url}" -At -c \
    "SELECT event_hash FROM event ORDER BY position DESC LIMIT 1")
  if [[ "${src_tail}" != "${dst_tail}" ]]; then
    echo "[drill] EVENT-HASH MISMATCH src=${src_tail} dst=${dst_tail}" >&2
    exit 1
  fi
  echo "[drill] event-hash tail matches: ${src_tail:-<empty>}"
  echo "[drill] OK $(date -u -Iseconds)"
}

# ---------------------------------------------------------------------------
# full mode (WAL-archive + base-backup + PITR)
# ---------------------------------------------------------------------------
#
# Pipeline:
#   1. Launch primary with archive_mode=on, archive_command writes
#      WAL segments into /backup/wal on a docker volume.
#   2. Create a tiny synthetic schema + 100 pre-base rows. The
#      schema mirrors the structure of the app's event table
#      (position, payload, event_hash) so the parity check is
#      semantically the same.
#   3. pg_basebackup the primary into /backup/base on the same
#      volume.
#   4. Write 50 MORE rows (post-base) on the primary.
#   5. Capture pg_current_wal_lsn + now() as the recovery target.
#   6. Force a WAL switch so the latest segment ships to the archive.
#   7. Stop primary.
#   8. Launch a fresh postgres container that mounts the same volume.
#      Its docker-entrypoint sees the empty PGDATA, untars the base
#      into PGDATA, writes restore_command + recovery_target_time +
#      recovery_target_action=promote into postgresql.auto.conf, and
#      touches recovery.signal.
#   9. Postgres replays WAL up to the recovery target, removes
#      recovery.signal, and promotes.
#  10. Verify rows = 150 (pre-base + post-base). If any rows are
#      missing the WAL-replay path is broken.

run_full() {
  echo "[drill] $(date -u -Iseconds)  mode=full"

  docker rm -f "${PRIMARY}" "${TARGET}" >/dev/null 2>&1 || true
  docker volume rm "${SHARED_VOL}" >/dev/null 2>&1 || true
  docker volume create "${SHARED_VOL}" >/dev/null

  echo "[drill] launching primary with WAL archiving"
  docker run -d --name "${PRIMARY}" \
    -e POSTGRES_PASSWORD=drill \
    -e POSTGRES_USER=drill \
    -e POSTGRES_DB=drill \
    -v "${SHARED_VOL}:/backup" \
    -p "${DST_PORT}:5432" \
    postgres:16 \
    -c wal_level=replica \
    -c archive_mode=on \
    -c "archive_command=test ! -f /backup/wal/%f && cp %p /backup/wal/%f" \
    -c archive_timeout=10 \
    -c max_wal_senders=3 \
    -c wal_keep_size=64MB >/dev/null
  wait_pg "${PRIMARY}"

  # The named docker volume is owned by root; chown to postgres so
  # the archive_command (which runs as postgres) can write WAL
  # segments + the basebackup output.
  docker exec --user 0 "${PRIMARY}" chown -R postgres:postgres /backup
  docker exec --user postgres "${PRIMARY}" mkdir -p /backup/wal

  echo "[drill] seeding synthetic schema + 100 pre-base rows"
  docker exec -u postgres "${PRIMARY}" psql -U drill drill -v ON_ERROR_STOP=1 -At -c "
    CREATE TABLE event (
      position BIGINT PRIMARY KEY,
      payload TEXT NOT NULL,
      event_hash TEXT NOT NULL
    );
    INSERT INTO event (position, payload, event_hash)
    SELECT g, 'pre-base-' || g, md5('pre' || g)
    FROM generate_series(1, 100) g;
  " >/dev/null

  echo "[drill] taking pg_basebackup into /backup/base"
  docker exec -u postgres "${PRIMARY}" rm -rf /backup/base
  docker exec -u postgres "${PRIMARY}" pg_basebackup \
    --pgdata=/backup/base \
    --format=plain \
    --wal-method=stream \
    --checkpoint=fast \
    --username=drill \
    --no-password

  echo "[drill] writing 50 post-base rows"
  docker exec -u postgres "${PRIMARY}" psql -U drill drill -v ON_ERROR_STOP=1 -At -c "
    INSERT INTO event (position, payload, event_hash)
    SELECT g, 'post-base-' || g, md5('post' || g)
    FROM generate_series(101, 150) g;
  " >/dev/null

  # Capture the LSN as the recovery target. LSN-based PITR is
  # deterministic — no clock drift, no archive_timeout race. Time
  # mode is documented in the runbook for the operator.
  local recovery_lsn
  recovery_lsn=$(docker exec -u postgres "${PRIMARY}" psql -U drill drill -At -c \
    "SELECT pg_current_wal_lsn();")
  echo "[drill] recovery_target_lsn = ${recovery_lsn}"

  # Force a WAL switch so the segment that holds the post-base writes
  # ships to the archive promptly (without waiting on archive_timeout).
  docker exec -u postgres "${PRIMARY}" psql -U drill drill -At -c \
    "SELECT pg_switch_wal();" >/dev/null
  docker exec -u postgres "${PRIMARY}" psql -U drill drill -At -c \
    "CHECKPOINT;" >/dev/null

  # Poll the archive directory until the target segment has shipped.
  # The segment for our LSN should be present once archive_command
  # runs (within archive_timeout).
  for _ in {1..20}; do
    if docker exec -u postgres "${PRIMARY}" sh -c 'ls -1 /backup/wal | wc -l' \
        | awk '{ exit !($1>=2) }'; then
      break
    fi
    sleep 1
  done

  echo "[drill] stopping primary"
  docker stop "${PRIMARY}" >/dev/null

  echo "[drill] preparing target PGDATA from base + recovery config"
  # Write recovery config + recovery.signal into the base data dir
  # via a tiny throwaway container so we don't need host root.
  docker run --rm -v "${SHARED_VOL}:/backup" alpine:3.20 sh -c "
    set -e
    cat >> /backup/base/postgresql.auto.conf <<EOF
restore_command = 'cp /backup/wal/%f %p'
recovery_target_lsn = '${recovery_lsn}'
recovery_target_action = 'promote'
EOF
    touch /backup/base/recovery.signal
    # Postgres requires PGDATA to be mode 0700.
    chmod -R 0700 /backup/base
  " >/dev/null

  echo "[drill] launching target on the restored data dir"
  docker run -d --name "${TARGET}" \
    -v "${SHARED_VOL}:/backup" \
    -e PGDATA=/backup/base \
    -p "${DST_PORT}:5432" \
    --entrypoint docker-entrypoint.sh \
    postgres:16 postgres >/dev/null

  # Wait for promotion. Postgres removes recovery.signal on promote;
  # we also poll pg_isready, which only returns 0 once the server
  # finishes recovery and accepts connections.
  echo "[drill] waiting for WAL replay + promotion"
  wait_pg "${TARGET}"

  # Sanity: recovery.signal should be gone.
  if docker exec "${TARGET}" test -f /backup/base/recovery.signal; then
    echo "[drill] FAILED: recovery.signal still present (promotion didn't fire)" >&2
    docker logs --tail=120 "${TARGET}" >&2 || true
    exit 1
  fi

  echo "[drill] verifying post-base rows are present"
  local rows
  rows=$(docker exec "${TARGET}" psql -U drill drill -At -c \
    "SELECT COUNT(*) FROM event")
  if [[ "${rows}" != "150" ]]; then
    echo "[drill] PARITY MISMATCH expected=150 got=${rows}" >&2
    docker exec "${TARGET}" psql -U drill drill -At -c \
      "SELECT MIN(position), MAX(position), COUNT(*) FROM event" >&2
    docker logs --tail=80 "${TARGET}" >&2 || true
    exit 1
  fi

  # Spot-check a post-base hash.
  local hash
  hash=$(docker exec "${TARGET}" psql -U drill drill -At -c \
    "SELECT event_hash FROM event WHERE position = 150")
  local expected_hash="$(printf 'post%s' 150 | md5sum | awk '{print $1}')"
  if [[ "${hash}" != "${expected_hash}" ]]; then
    echo "[drill] HASH MISMATCH on post-base row 150 got=${hash} want=${expected_hash}" >&2
    exit 1
  fi
  echo "[drill] verified 150 rows (100 pre-base + 50 post-base, all replayed)"
  echo "[drill] OK $(date -u -Iseconds)"
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

if [[ "${MODE}" == "smoke" ]]; then
  run_smoke
else
  run_full
fi
