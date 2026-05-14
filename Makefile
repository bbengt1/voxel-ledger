# Voxel Ledger — local-dev convenience targets.
#
# Every target is phony and idempotent unless explicitly noted (e.g. `nuke`).
# Run `make help` for a catalogue. The bootstrap pipeline is composed from
# smaller phony targets so each step can be re-run independently.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

COMPOSE       := scripts/compose.sh
ENV_FILE      := .env.dev
BACKEND_SVC   := backend
DB_SVC        := db

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this catalogue
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_.-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
# Bootstrap pipeline
# ---------------------------------------------------------------------------

.PHONY: bootstrap
bootstrap: check-tools env-dev install up wait-healthy migrate seed summary ## One-command local bootstrap (idempotent)

.PHONY: check-tools
check-tools: ## Verify Python/Node/pnpm/Docker versions
	@scripts/check_tools.sh

.PHONY: env-dev
env-dev: ## Generate .env.dev with random local secrets (if missing)
	@scripts/gen_env_dev.sh

.PHONY: install
install: ## Install backend (editable) and frontend (pnpm) deps
	@echo "make install: backend (editable)"
	@python3 -m pip install -e "backend/[dev]"
	@echo "make install: frontend (pnpm)"
	@pnpm install

.PHONY: up
up: ## Bring up the dev compose stack (-d --build)
	@$(COMPOSE) up -d --build

.PHONY: wait-healthy
wait-healthy: ## Wait until db + backend healthchecks pass
	@echo "wait-healthy: polling docker compose status..."
	@for svc in $(DB_SVC) $(BACKEND_SVC); do \
	    echo "  waiting for $$svc..."; \
	    for i in $$(seq 1 60); do \
	        cid=$$($(COMPOSE) ps -q $$svc 2>/dev/null || true); \
	        if [ -z "$$cid" ]; then sleep 2; continue; fi; \
	        status=$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$$cid" 2>/dev/null || echo unknown); \
	        if [ "$$status" = "healthy" ] || [ "$$status" = "running" ]; then echo "    $$svc: $$status"; break; fi; \
	        sleep 2; \
	        if [ "$$i" = "60" ]; then echo "    $$svc never reached healthy: $$status" >&2; exit 1; fi; \
	    done; \
	done

.PHONY: migrate
migrate: ## Run alembic upgrade head inside the backend container
	@$(COMPOSE) exec -T $(BACKEND_SVC) alembic upgrade head

# Seeds run on the host (with the editable backend install on $PATH) rather
# than inside the container — the container source mount is `./backend:/app`,
# which doesn't include `scripts/`. We export the env vars from .env.dev and
# rewrite the DATABASE_URL host so localhost works from the host process.
.PHONY: seed
seed: ## (Re-)run owner seed (idempotent)
	@set -a; . ./$(ENV_FILE); set +a; \
	    DATABASE_URL="$$(echo "$$DATABASE_URL" | sed 's|@db:|@localhost:|')" \
	    python3 -m scripts.seed_owner

.PHONY: seed-fixtures
seed-fixtures: ## Run opt-in dev fixtures (idempotent)
	@set -a; . ./$(ENV_FILE); set +a; \
	    DATABASE_URL="$$(echo "$$DATABASE_URL" | sed 's|@db:|@localhost:|')" \
	    python3 -m scripts.seed_dev

.PHONY: summary
summary: ## Print URLs and login info after bootstrap
	@set -a; [ -f $(ENV_FILE) ] && . ./$(ENV_FILE); set +a; \
	    echo ""; \
	    echo "Voxel Ledger dev stack is up."; \
	    echo "  Frontend:  http://localhost:$${FRONTEND_HOST_PORT:-5173}"; \
	    echo "  Backend:   http://localhost:$${BACKEND_HOST_PORT:-8000}  (docs: /docs)"; \
	    echo "  Postgres:  localhost:$${POSTGRES_HOST_PORT:-5432}"
	@echo ""
	@echo "Owner credentials are in $(ENV_FILE) (OWNER_EMAIL / OWNER_PASSWORD)."
	@echo "Useful: make logs | make down | make nuke | make test"

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

.PHONY: dev
dev: up logs ## Bring stack up and tail logs

.PHONY: down
down: ## Stop containers (volumes preserved)
	@$(COMPOSE) down

.PHONY: nuke
nuke: ## Stop everything and remove volumes (destructive)
	@read -p "This destroys all local dev data (containers + volumes). Type 'yes' to continue: " ans && [ "$$ans" = "yes" ] || { echo "aborted."; exit 1; }
	@$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail logs from all services
	@$(COMPOSE) logs -f

.PHONY: psql
psql: ## Open a psql shell against the dev DB
	@$(COMPOSE) exec $(DB_SVC) sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

.PHONY: test
test: test-backend test-frontend ## Run backend + frontend tests against the running stack

.PHONY: test-backend
test-backend: ## Run pytest -q inside the backend container
	@$(COMPOSE) exec -T $(BACKEND_SVC) pytest -q

.PHONY: test-frontend
test-frontend: ## Run pnpm test on the host
	@pnpm --filter @voxel-ledger/frontend test
