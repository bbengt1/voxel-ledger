# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Voxel Ledger backend image.
#
# Stages:
#   - base:    common Python runtime + system deps (curl for healthcheck,
#              libpq for psycopg/asyncpg runtime niceties).
#   - builder: installs the project (no dev deps) into a venv we can copy.
#   - dev:     installs project with [dev] extras; uvicorn --reload is wired
#              up via docker-compose so we keep the Dockerfile generic.
#   - runtime: lean production image. No dev deps. Entrypoint runs
#              `alembic upgrade head` then exec's uvicorn. SKIP_MIGRATIONS=1
#              short-circuits the migration step (emergency code-only deploys).
# -----------------------------------------------------------------------------

ARG PYTHON_VERSION=3.13-slim

FROM python:${PYTHON_VERSION} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# --- builder ----------------------------------------------------------------
FROM base AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv "$VIRTUAL_ENV"
WORKDIR /app
COPY pyproject.toml ./
# Install runtime dependencies only. We resolve from pyproject (no lockfile yet).
RUN pip install --upgrade pip \
    && pip install .

# --- dev --------------------------------------------------------------------
FROM builder AS dev
WORKDIR /app
RUN pip install ".[dev]"
COPY . .
EXPOSE 8000
# uvicorn command is supplied by docker-compose so dev can override flags.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- runtime ----------------------------------------------------------------
FROM base AS runtime
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY . .
# Non-root user. Uid/gid match common dev defaults; override at runtime if
# you need to match a host-mounted volume's ownership.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app
USER app
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
