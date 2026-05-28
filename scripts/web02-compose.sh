#!/usr/bin/env bash
# Thin alias: web02-compose.sh — invokes the prod compose stack on web02.
#
# web02 is the v2 production host. Delegates to `scripts/compose.sh --prod`
# with `ENV_FILE` pinned to the web02 server env file so the host path is
# baked into the wrapper instead of every operator's muscle memory.
#
# Usage (on web02):
#   cd /srv/voxel-ledger/repo
#   scripts/web02-compose.sh up -d --build
#   scripts/web02-compose.sh logs -f --tail=200 backend
#   scripts/web02-compose.sh ps
#
# All arguments are forwarded verbatim to `scripts/compose.sh --prod`.

set -euo pipefail

export ENV_FILE="${ENV_FILE:-/srv/voxel-ledger/env/web02.env}"
exec "$(dirname "$0")/compose.sh" --prod "$@"
