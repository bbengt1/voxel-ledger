#!/usr/bin/env bash
# Re-export the FastAPI OpenAPI spec to frontend/src/api/openapi.json.
#
# Thin shim around `python -m scripts.export_openapi`. Exists mainly to
# pick a workable Python interpreter without forcing every contributor (and
# every CI image) to put `python` on the PATH. Order of preference:
#   1. $VOXEL_LEDGER_PYTHON           — explicit override
#   2. backend/.venv/bin/python       — the local backend venv
#   3. python                         — system python (some envs only)
#   4. python3                        — the everywhere-else fallback
#
# Run from the repo root.

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -n "${VOXEL_LEDGER_PYTHON:-}" ]]; then
  PY="${VOXEL_LEDGER_PYTHON}"
elif [[ -x "backend/.venv/bin/python" ]]; then
  PY="backend/.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PY="python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "export-openapi.sh: no python interpreter found" >&2
  exit 1
fi

exec "${PY}" -m scripts.export_openapi
