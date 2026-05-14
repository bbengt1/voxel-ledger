"""Deterministically export the backend OpenAPI spec to disk.

This is the single source of truth for the contract that drives the frontend
codegen pipeline (see docs/openapi-codegen.md and issue #5).

Why a script instead of `curl http://localhost:8000/api/v1/openapi.json`?
- No running server required: we import the FastAPI app and call
  `app.openapi()` directly. That means no DB, no port collisions, and no
  flaky timing in CI.
- Deterministic output: keys sorted, two-space indent, trailing newline,
  utf-8 with `ensure_ascii=False`. Two consecutive runs produce
  byte-identical bytes — that's what makes `git diff --exit-code` a
  meaningful drift check.

Run from the repo root:

    python -m scripts.export_openapi

It writes to `frontend/src/api/openapi.json`. The frontend `codegen:export`
npm script wraps this.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> int:
    repo_root = _repo_root()
    backend_root = repo_root / "backend"

    # Make `app.*` importable without requiring `pip install -e backend`.
    sys.path.insert(0, str(backend_root))

    # Belt-and-braces: keep app import side-effect free. The conftest already
    # uses TESTING=true to disable real DB engine work, but the FastAPI app
    # factory itself doesn't touch the DB at import time — the lifespan does,
    # and we never enter the lifespan here.
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("ENVIRONMENT", "test")
    # Provide harmless placeholders so settings validation doesn't refuse to
    # start when no .env is present (e.g. in CI).
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/voxel_ledger_codegen"
    )
    os.environ.setdefault("JWT_SECRET_KEY", "codegen-export-not-a-real-secret-1234567890")
    os.environ.setdefault("OWNER_EMAIL", "codegen@example.invalid")
    os.environ.setdefault("OWNER_PASSWORD", "codegen-export-placeholder-pw-1234567890")

    # Import after sys.path + env setup above.
    from app.main import app

    spec = app.openapi()

    out_path = repo_root / "frontend" / "src" / "api" / "openapi.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out_path.write_text(payload, encoding="utf-8")

    print(f"wrote {out_path.relative_to(repo_root)} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
