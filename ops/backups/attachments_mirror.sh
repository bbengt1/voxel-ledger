#!/usr/bin/env bash
# Nightly rsync of ATTACHMENTS_STORAGE_ROOT to off-site (Phase 12.2,
# #204). Bandwidth-throttled so it doesn't compete with daytime
# traffic when the timer slips.
#
# Env:
#   ATTACHMENTS_STORAGE_ROOT  source dir (matches the Settings value)
#   OFFSITE_RSYNC             target, e.g. "user@host:/srv/voxel/attachments/"
#   BWLIMIT                   kilobytes/sec (default: 5000 = ~5 MB/s)

set -euo pipefail

SRC="${ATTACHMENTS_STORAGE_ROOT:?ATTACHMENTS_STORAGE_ROOT required}"
DEST="${OFFSITE_RSYNC:?OFFSITE_RSYNC required}"
BWLIMIT="${BWLIMIT:-5000}"

echo "[attachments_mirror] $(date -u -Iseconds)  ${SRC} -> ${DEST}  (${BWLIMIT}KB/s cap)"

rsync \
  --archive \
  --delete-after \
  --partial \
  --bwlimit="${BWLIMIT}" \
  --info=stats1,progress2 \
  "${SRC%/}/" "${DEST%/}/"

echo "[attachments_mirror] done $(date -u -Iseconds)"
