"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.db import dispose_engine, make_engine, set_engine
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware
from app.core.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI app.

    Factored so tests can inject a Settings instance instead of relying on
    process env.
    """
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings)
        set_engine(engine)
        log.info(
            "app.startup",
            app=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )
        try:
            yield
        finally:
            await dispose_engine()
            log.info("app.shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        # Serve the OpenAPI spec (and Swagger/Redoc docs) under the same
        # /api/v1 prefix as every business endpoint so the frontend codegen
        # has a single, symmetric URL to fetch. See docs/openapi-codegen.md.
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
    )
    app.state.settings = settings
    app.add_middleware(RequestIdMiddleware)

    # CORS is opt-in via settings.cors_origins. Empty list = no middleware =
    # browser cross-origin calls are blocked (server-to-server only). Local
    # dev env files seed http://localhost:5173 so the Vite frontend works.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # /health is intentionally unversioned — it's an infra contract, not a
    # business API. Everything else hangs off /api/v1.
    app.include_router(health_router)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
