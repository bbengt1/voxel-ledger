#!/usr/bin/env bash
# Thin wrapper around `docker compose` that picks the right compose file and
# env file based on the desired stack.
#
# Selection rules (first match wins):
#   1. Explicit `--prod` / `--dev` flag (consumed; not forwarded).
#   2. The ENV environment variable: `ENV=prod` selects prod, anything else
#      (including unset) selects dev.
#
# All remaining arguments are forwarded to `docker compose`, so:
#   scripts/compose.sh up -d --build
#   scripts/compose.sh --prod up -d --build
#   ENV=prod scripts/compose.sh ps
#
# The selected env file is passed via `--env-file`, which makes the variables
# available for compose interpolation. Per-service `env_file:` entries in the
# compose YAML pull in the same file for runtime container env.

set -euo pipefail

stack=""
forward_args=()

for arg in "$@"; do
    case "$arg" in
        --prod) stack="prod" ;;
        --dev)  stack="dev" ;;
        *) forward_args+=("$arg") ;;
    esac
done

if [ -z "$stack" ]; then
    if [ "${ENV:-}" = "prod" ] || [ "${ENV:-}" = "production" ]; then
        stack="prod"
    else
        stack="dev"
    fi
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

case "$stack" in
    dev)
        compose_file="docker-compose.yml"
        env_file=".env.dev"
        ;;
    prod)
        compose_file="docker-compose.prod.yml"
        # On web01 this lives outside the repo. Allow override via $ENV_FILE.
        env_file="${ENV_FILE:-/srv/3d-print-sales/env/web01.env}"
        ;;
    *)
        echo "compose.sh: unknown stack '$stack'" >&2
        exit 2
        ;;
esac

if [ ! -f "$env_file" ]; then
    echo "compose.sh: env file not found at '$env_file'" >&2
    if [ "$stack" = "dev" ]; then
        echo "  hint: cp .env.dev.example .env.dev" >&2
    else
        echo "  hint: populate $env_file from .env.prod.example" >&2
    fi
    exit 1
fi

echo "compose.sh: stack=$stack file=$compose_file env=$env_file" >&2
exec docker compose --env-file "$env_file" -f "$compose_file" "${forward_args[@]}"
