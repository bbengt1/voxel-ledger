# print-sales-v2 — Rewrite Documentation Set

This folder contains reverse-engineered documentation of the existing 3D Print Sales application, intended to support a clean rewrite. Each document captures **what the system does** and **why**, deliberately decoupled from the current implementation so a new team can build a replacement on whatever stack is appropriate.

## Documents

1. [01_system_overview.md](01_system_overview.md) — Executive summary
2. [02_functional_requirements.md](02_functional_requirements.md) — Features and use cases
3. [03_non_functional_requirements.md](03_non_functional_requirements.md) — Performance, security, reliability
4. [04_architecture.md](04_architecture.md) — High-level architecture
5. [05_data_model.md](05_data_model.md) — Entities and data dictionary
6. [06_api_catalog.md](06_api_catalog.md) — REST API surface
7. [07_module_specifications.md](07_module_specifications.md) — Per-module logic
8. [08_ui_ux.md](08_ui_ux.md) — Screen inventory, flows, UX laws
9. [09_security_compliance.md](09_security_compliance.md) — Threat model, auth, audit
10. [10_testing.md](10_testing.md) — Test coverage and scenarios
11. [11_operations_deployment.md](11_operations_deployment.md) — Build, deploy, monitor
12. [12_glossary_assumptions_decisions.md](12_glossary_assumptions_decisions.md) — Terms, assumptions, trade-offs

### Auto-generated API reference

These are produced directly from the live FastAPI OpenAPI spec — not hand-written.

- [openapi.json](openapi.json) — raw spec (271 paths, 315 schemas)
- [api_overview.md](api_overview.md) — endpoint counts per tag
- [api_endpoints.md](api_endpoints.md) — every operation with params, body, responses
- [api_schemas.md](api_schemas.md) — every component schema with fields, types, required flags

Regenerate after backend changes:
```
TESTING=true SECRET_KEY=... ADMIN_PASSWORD=... DB_PASSWORD=... \
  DATABASE_URL=sqlite+aiosqlite:///./test.db \
  python -c "import json; from app.main import app; \
    json.dump(app.openapi(), open('print-sales-v2/openapi.json','w'), indent=2)"
python /tmp/dump_openapi_md.py
```

## Reading Order

Read 01 → 02 first to understand the *what*. Then 04 → 05 for the *how* at high level. Deep-dive 06 → 07 → 08 as needed. Cross-cutting concerns live in 03, 09, 11. The glossary (12) is a lookup.

## Source Snapshot

- Source repo: `3d-print-sales`
- Reverse-engineered: 2026-05-13
- Source stack (current, not prescriptive for v2): Python 3.13 / FastAPI / SQLAlchemy 2 async / PostgreSQL 16 / React 19 / TypeScript / Vite / Tailwind 4 / Zustand / TanStack Query
- Live host: `web01.internal`, Docker Compose deploy

The new system is not required to preserve the source stack; documents intentionally describe behavior rather than implementation.
