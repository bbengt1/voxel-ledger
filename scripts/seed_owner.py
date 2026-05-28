"""Thin shim that delegates to `app.seed.owner`.

The canonical implementation lives in `backend/app/seed/owner.py` so it's
present inside the backend image. This top-level shim is retained so dev
and CI workflows that have learned `python -m scripts.seed_owner` keep
working — Makefile, docs/development.md, the env-gen script, and CI YAML
all reference this entrypoint.

Production deploys run `python -m app.seed.owner` from the backend
entrypoint (see `backend/docker/entrypoint.sh`); the top-level `scripts/`
package is not bundled into the backend image.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/seed_owner.py` from repo root by ensuring
# `backend/` is importable. `python -m scripts.seed_owner` works regardless.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _REPO_ROOT / "backend"
if _BACKEND.exists() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Re-export so tests that monkeypatch `scripts.seed_owner.load_settings`
# keep working transparently. (The newer canonical path is
# `app.seed.owner.load_settings`; this shim mirrors the same binding.)
from app.seed.owner import load_settings, main, seed  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
