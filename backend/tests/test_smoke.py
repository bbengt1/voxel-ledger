"""Smoke tests: import surface + app construction."""

from __future__ import annotations


def test_imports() -> None:
    import app
    import app.api.v1.health
    import app.api.v1.router
    import app.core.db
    import app.core.logging
    import app.core.middleware
    import app.core.settings
    import app.main  # noqa: F401


def test_app_factory_builds(settings) -> None:
    from app.main import create_app

    app = create_app(settings=settings)
    routes = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/health" in routes
