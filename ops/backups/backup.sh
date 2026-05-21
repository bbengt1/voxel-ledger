#!/usr/bin/env bash
# Nightly Postgres backup (Phase 12.2, #204).
#
# Takes a pg_basebackup tarball + manifest, drops it under
# ${BACKUP_ROOT}, and prunes older artifacts per the rotation policy:
#   - last 30 daily snapshots
#   - last 12 monthly snapshots (1st of each month, retained beyond
#     the daily window)
#
# Designed to be invoked from systemd timer or cron. Idempotent: a
# repeated run within the same minute will produce a new artifact;
# the rotation step still applies.
#
# Env contract (all required unless noted):
#   PGHOST         (default: localhost)
#   PGPORT         (default: 5432)
#   PGUSER         postgres role with REPLICATION privilege
#   PGPASSWORD     password for $PGUSER (or use ~/.pgpass)
#   BACKUP_ROOT    directory artifacts land in
#   OFFSITE_RSYNC  optional rsync target, e.g. "user@host:/srv/backups/"

set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:?PGUSER required}"
BACKUP_ROOT="${BACKUP_ROOT:?BACKUP_ROOT required}"
STAMP="$(date -u +'%Y%m%dT%H%M%SZ')"
DEST="${BACKUP_ROOT}/${STAMP}"

mkdir -p "${DEST}"

echo "[backup] $(date -u -Iseconds)  starting pg_basebackup -> ${DEST}"

pg_basebackup \
  --host="${PGHOST}" \
  --port="${PGPORT}" \
  --username="${PGUSER}" \
  --pgdata="${DEST}/base" \
  --format=tar \
  --gzip \
  --progress \
  --checkpoint=fast \
  --wal-method=stream \
  --no-password \
  --verbose

# Manifest hash for restore-time sanity.
(cd "${DEST}" && sha256sum base/*.tar.gz > manifest.sha256)

echo "[backup] base+manifest done. Size: $(du -sh "${DEST}" | cut -f1)"

# Off-site mirror (optional but the documented production path).
if [[ -n "${OFFSITE_RSYNC:-}" ]]; then
  echo "[backup] rsyncing to ${OFFSITE_RSYNC}"
  rsync --archive --bwlimit=10000 --partial --info=stats1 \
    "${DEST}/" "${OFFSITE_RSYNC%/}/${STAMP}/"
fi

# --- Rotation ---------------------------------------------------------------
echo "[backup] rotating old artifacts under ${BACKUP_ROOT}"

# Resolve a stable "now" so each find runs against the same cutoff.
NOW_EPOCH="$(date +%s)"
THIRTY_DAYS_AGO=$(( NOW_EPOCH - 30*86400 ))
ONE_YEAR_AGO=$(( NOW_EPOCH - 365*86400 ))

while IFS= read -r -d '' dir; do
  name="$(basename "${dir}")"
  # Expect names like YYYYmmddTHHMMSSZ.
  [[ "${name}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || continue

  # macOS + BSD `date` don't grok %s with -d; parse with gnu form first.
  if dt_epoch=$(date -j -f '%Y%m%dT%H%M%SZ' "${name}" +%s 2>/dev/null); then
    :  # macOS path
  elif dt_epoch=$(date -d "${name:0:8} ${name:9:2}:${name:11:2}:${name:13:2}" +%s 2>/dev/null); then
    :  # GNU path
  else
    continue
  fi

  if (( dt_epoch >= THIRTY_DAYS_AGO )); then
    continue                              # inside daily window
  fi
  if (( dt_epoch < ONE_YEAR_AGO )); then
    rm -rf -- "${dir}"
    echo "[backup] purged (>1y): ${name}"
    continue
  fi

  # In the 30d..1y range, keep only the first-of-month snapshot.
  day="${name:6:2}"
  if [[ "${day}" != "01" ]]; then
    rm -rf -- "${dir}"
    echo "[backup] purged (non-monthly): ${name}"
  fi
done < <(find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -print0)

echo "[backup] done $(date -u -Iseconds)"
