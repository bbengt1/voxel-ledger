"""Phase 5.4 invariant: the printer monitor is LAZY-LOADED.

App startup (``create_app`` + lifespan + a ``/health`` round-trip) MUST
NOT import ``app.services.printer_monitor``. Running this assertion
inside the same pytest process as other tests is unreliable — those
tests deliberately import the monitor — so we spawn a clean Python
subprocess to verify the boot-only path.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = textwrap.dedent(
    """
    import asyncio
    import os
    import sys

    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-a-real-secret-xx")
    os.environ.setdefault("BCRYPT_ROUNDS", "4")

    from httpx import ASGITransport, AsyncClient
    from app.main import create_app
    from app.core.settings import Settings

    async def main() -> None:
        settings = Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            jwt_secret_key="test-secret-key-not-a-real-secret-xx",
            bcrypt_rounds=4,
            environment="test",
            testing=True,
        )
        app = create_app(settings=settings)
        transport = ASGITransport(app=app)
        async with (
            AsyncClient(transport=transport, base_url="http://testserver") as ac,
            app.router.lifespan_context(app),
        ):
            r = await ac.get("/health")
            assert r.status_code == 200, r.status_code

        leaked = [
            n for n in sys.modules if n.startswith("app.services.printer_monitor")
        ]
        assert leaked == [], f"printer_monitor leaked into sys.modules: {leaked}"
        print("ok")

    asyncio.run(main())
    """
)


def test_monitor_module_not_imported_on_boot() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    backend = repo_root / "backend"
    env = {
        "PYTHONPATH": f"{backend}:{repo_root}",
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert (
        result.returncode == 0
    ), f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "ok" in result.stdout
