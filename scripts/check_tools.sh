#!/usr/bin/env bash
# Verify required local-dev tooling is present and at a recent enough version.
# Exits non-zero on the first failure with a clear message.

set -euo pipefail

MIN_PYTHON="3.12"
MIN_NODE="20.11"
MIN_PNPM="9"

fail() {
    echo "check_tools: $*" >&2
    exit 1
}

# Return 0 if $1 >= $2 (dotted version compare).
version_ge() {
    # Trick: sort -V; if min sorts first or equal, current >= min.
    [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

check_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "missing required tool: $1"
}

echo "check_tools: verifying local dev toolchain"

# Python
check_cmd python3
py_ver="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
version_ge "$py_ver" "$MIN_PYTHON" \
    || fail "python3 $py_ver < required $MIN_PYTHON"
echo "  python3 $py_ver  ok"

# Node
check_cmd node
node_ver="$(node --version | sed 's/^v//')"
version_ge "$node_ver" "$MIN_NODE" \
    || fail "node $node_ver < required $MIN_NODE"
echo "  node $node_ver  ok"

# pnpm (corepack will pin the exact version from package.json, but we need
# the binary on PATH for `make bootstrap` to invoke pnpm install).
if ! command -v pnpm >/dev/null 2>&1; then
    if command -v corepack >/dev/null 2>&1; then
        echo "  pnpm not on PATH; trying 'corepack enable'..."
        corepack enable >/dev/null 2>&1 || true
    fi
fi
check_cmd pnpm
pnpm_ver="$(pnpm --version)"
version_ge "$pnpm_ver" "$MIN_PNPM" \
    || fail "pnpm $pnpm_ver < required $MIN_PNPM"
echo "  pnpm $pnpm_ver  ok"

# Docker
check_cmd docker
docker info >/dev/null 2>&1 \
    || fail "docker is installed but the daemon is not reachable; start Docker Desktop / dockerd"
echo "  docker  ok"

# docker compose v2 plugin
docker compose version >/dev/null 2>&1 \
    || fail "docker compose v2 plugin is not available (try: docker compose version)"
echo "  docker compose  ok"

# openssl, for secret generation
check_cmd openssl
echo "  openssl  ok"

echo "check_tools: all good"
