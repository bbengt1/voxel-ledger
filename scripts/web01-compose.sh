#!/usr/bin/env bash
# Thin alias: web01-compose.sh — invokes the prod compose stack.
#
# Kept for muscle memory and historical references in agents.md, the operations
# spec, and the n8n deploy workflow. Delegates to the canonical
# `scripts/compose.sh` wrapper with `--prod` injected, so behavior stays in one
# place.
#
# Usage (on web01):
#   cd /srv/3d-print-sales/repo
#   scripts/web01-compose.sh up -d --build
#   scripts/web01-compose.sh logs -f --tail=200 backend
#   scripts/web01-compose.sh ps
#
# All arguments are forwarded verbatim to `scripts/compose.sh --prod`.

set -euo pipefail

exec "$(dirname "$0")/compose.sh" --prod "$@"
