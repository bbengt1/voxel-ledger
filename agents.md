# Agents Guide

## Overview

- This repository is a **ground-up rewrite** of the 3D-print business app currently deployed on `web01`. The legacy app remains in production while v2 is being built.
- Specifications live under [`print-sales-v2/`](print-sales-v2/). The implementation plan is [`print-sales-v2/IMPLEMENTATION_PLAN.md`](print-sales-v2/IMPLEMENTATION_PLAN.md).
- Backend target: FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16, pytest.
- Frontend target: React 19, TypeScript, Vite, Tailwind 4 + Radix, TanStack Query 5, Zustand 5.
- Bounded contexts (organize code by these, not by technical layer): Identity & Access, Catalog, Inventory, Production, Sales, AR, AP, Banking, Accounting, Reporting, Notifications, Platform.
- Core architectural choices the rewrite must honor:
  - **Event-sourced accounting.** Domain events are the source of truth; journal entries, balances, projections, and reports are derived. Append-only event log with hash chain and `schema_version` upcasting.
  - **Race-safe reference numbering** via DB-sequence allocator (`{PREFIX}-{YYYY}-{NNNN}`). Never `COUNT(*)`.
  - **Frontend types generated from OpenAPI** at prebuild; CI fails on drift. No hand-typed resource shapes.
  - **RBAC with named roles**: `owner`, `bookkeeper`, `production`, `sales`, `viewer`, deny-by-default.
  - **Postgres-native job queue** (pg-boss / pgmq + Arq). No Redis/RabbitMQ.
  - **Lazy-loaded printer monitoring.** Moonraker WS must not be a startup dependency (real v1 incident).
  - **Single-tenant, USD-only, no MFA/SSO, no staging environment.** See [`print-sales-v2/12_glossary_assumptions_decisions.md`](print-sales-v2/12_glossary_assumptions_decisions.md).

## Repository Map

- [`print-sales-v2/`](print-sales-v2/) — authoritative specs for the rewrite. **Treat these as the source of truth for what to build.**
  - `01_system_overview.md` through `12_glossary_assumptions_decisions.md` — narrative specs.
  - `IMPLEMENTATION_PLAN.md` — phased build plan.
  - `openapi.json`, `api_endpoints.md`, `api_schemas.md`, `api_overview.md` — API surface reference (legacy v1 export; use as a contract starting point, not a hard target).
- New code will live under `backend/` and `frontend/` once Phase 0 lands. Until then, the repo holds specs only.

## Working Rules

- **Read the spec first.** Every meaningful change should trace back to a spec section or implementation-plan phase. If the spec is wrong or ambiguous, update the spec in the same PR.
- Keep API, schema, model, and frontend types in lockstep. The OpenAPI → TS codegen pipeline is the enforcement mechanism — don't bypass it.
- Business logic lives in the **service layer**. Routers stay thin. React components do not contain business rules.
- All accounting mutations post to the event log inside the same DB transaction as the side effect (inventory, ledger). No async fire-and-forget for financial state.
- Inventory and accounting are tightly coupled. Sales, refunds, receipts, settlements, and production all have ledger side effects — wire them through the event store, not direct table writes.
- Honor the v2 won't-do list (multi-currency, MFA/SSO, S3 attachments, staging, heavy job brokers). Pushing past these requires an explicit decision-record update.
- Treat GitHub issues as the source of truth for all work. Tie every change to an issue.
- When asked to create an issue, use plan mode and produce a detailed, actionable issue with scope, constraints, acceptance criteria, and validation steps.
- Ask clarifying questions when requirements are materially ambiguous or the wrong assumption would create rework.
- Default to expert recommendations, but user direction overrides when explicitly provided.
- Before considering any issue complete, update affected repository documentation (specs included) so it stays current and detailed.

## Deployment Targets

The v2 app deploys to `web02.internal`. The legacy v1 app continues to
run on `web01.internal` until v2 cutover; see
[`docs/web01_runbook.md`](docs/web01_runbook.md) for v1 ops.

- **Canonical deploy path: the `web02-deploy` n8n workflow** at [`ops/n8n/web02-deploy.json`](ops/n8n/web02-deploy.json), executed from `n8n.internal`. It encapsulates pull → migrate → rebuild → verify with per-step observability. Operator runbook: [`docs/web02_n8n_deploy.md`](docs/web02_n8n_deploy.md).
- **Fallback: manual SSH flow.** [`docs/web02_runbook.md`](docs/web02_runbook.md). Use it when n8n is unavailable, when debugging a broken deploy, or for one-off operations (e.g. `alembic downgrade`, emergency restart).
- **First-time host setup:** [`docs/web02_bootstrap.md`](docs/web02_bootstrap.md).
- Live host: `deploy@web02.internal` (SSH alias `web02`).
- App root on host: `/srv/voxel-ledger`
- Repo checkout on host: `/srv/voxel-ledger/repo`
- Server env file: `/srv/voxel-ledger/env/web02.env` (template at [`.env.web02.example`](.env.web02.example))
- Systemd unit: `voxel-ledger.service`
- Compose wrapper: `/srv/voxel-ledger/repo/scripts/web02-compose.sh`
- Host-side deploy wrapper: `/srv/voxel-ledger/deploy.sh` (invokes `scripts/deploy.sh` with `COMPOSE=scripts/web02-compose.sh`)
- Public URL: **https://print.bengtsonprecision3d.com/** (Cloudflare Tunnel → `web02:80`). Internally the host serves plain HTTP on port 80; TLS terminates at Cloudflare.
- **Migrations must run on every schema-changing deploy.** Backend startup queries newly-added tables/columns; skipping migrations crashes the container. (Real v1 incident on 2026-05-09 with PR #271 / #239.) Use `SKIP_MIGRATIONS=1` only for code-only emergency redeploys when you know there's no schema delta.
- Container names: `3d-print-sales-db`, `3d-print-sales-backend`, `3d-print-sales-frontend`, `3d-print-sales-nginx` (the `container_name` fields predate the rename; the compose `name:` is `voxel-ledger`).
- Before deploying, ensure the target commit/branch is correct on the server checkout and that required migrations, docs, tests, and validation are already complete.
- After deploying, verify container health, backend health, and frontend reachability before calling the work live.

## Validation

- Backend tests (once `backend/` exists): `python3 -m pytest backend/tests -q`
- Frontend build (once `frontend/` exists): `cd frontend && npm run build`
- OpenAPI → TS drift check (CI-enforced once codegen is wired): regenerate `frontend/src/api/types.ts` and `git diff --exit-code`.
- Replay test: rebuild projections from the event log and assert read-model parity (nightly + on-demand).
- Prefer targeted pytest runs while iterating; rerun the broader suite before declaring done.
- All delivered work should include testing and validation appropriate to the change. Do not treat implementation alone as done.
- If work is intended to go live, complete local validation first, then verify deployment on `web02` with post-deploy checks.
- Standard post-deploy checks on `web02`:
  - `cd /srv/voxel-ledger/repo && scripts/web02-compose.sh ps`
  - `curl -fsS http://127.0.0.1/health`
  - `curl -I http://127.0.0.1/`
- Review recent logs when the change affects startup, migrations, API routing, auth, printer monitoring, or frontend assets.

## Known Risks (v2 design-time)

- **Event log as hotspot.** bigserial PK is fine for current write volume; plan to partition by month and snapshot projections if `position` exceeds tens of millions.
- **Projection drift.** Handlers must be idempotent; ship a nightly replay test and a `verify_chain` admin endpoint from day one.
- **Moonraker WS as a startup dep.** v1 made this mistake. In v2, the printer-monitor module is lazy-loaded and never blocks app boot.
- **Reference allocator races.** Must use row-locked sequence (`UPDATE ... RETURNING`), not `COUNT(*)`. Cover with property tests.
- **Frontend type drift.** Mitigated by OpenAPI codegen + CI diff. Do not hand-edit generated files.
- **Single-VM hardware failure.** Mitigated by tested PITR restore and a documented runbook; RPO ≤ 24 h, RTO ≤ 2 h.
- **Scope creep into v1 features.** Honor explicit v2 won't-do list.

## PostgreSQL Strict Typing — Hard-Learned Patterns

PG strict-types ENUM columns. SQLite is permissive. The codebase has hit four distinct shapes of this gotcha; every new migration / model / query needs to honor the rules below. See the PRs cited for each — they have full diffs.

### 1. Migration: new ENUM type — DO NOT pre-create

Reference the enum on a column with `sa.Enum(*VALUES, name="...")` and let `op.create_table` auto-create the PG type via its dialect hook. Do **not** call `sa.Enum(...).create(bind, checkfirst=True)` first — `create_type=False` on the column is **not** honored by `_on_table_create`, so the auto-create still fires and you get `DuplicateObjectError: type "..." already exists`. (Fixed once in [#49](https://github.com/bbengt1/voxel-ledger/pull/49); the pattern crept back in `0011_product_bom` and `0012_custom_fields` and got fixed again with the same diff.)

### 2. Migration: reference an existing ENUM created by an earlier migration

Use the dialect-specific class with `create_type=False`. `sa.Enum(..., create_type=False)` (the generic class) does **not** suppress the auto-create — only `postgresql.ENUM(..., create_type=False)` does, because the dialect class actually checks the flag in its `create()` short-circuit. Branch by dialect:

```python
if bind.dialect.name == "postgresql":
    entity_kind_col_type = postgresql.ENUM(*VALUES, name="inventory_entity_kind", create_type=False)
else:
    entity_kind_col_type = sa.Enum(*VALUES, name="inventory_entity_kind")
```

(Bug + fix: [#60](https://github.com/bbengt1/voxel-ledger/pull/60).)

### 3. ORM column declaration for an ENUM

Always `SAEnum(*VALUES, name="account_type", create_type=False)`. Never `String(N)`. If the model declares String but the column is actually a PG enum, every `WHERE col = 'literal'` fails with `operator does not exist: account_type = character varying`. (Bug + fix: [#55](https://github.com/bbengt1/voxel-ledger/pull/55) for `product_bom_item.component_kind`.)

### 4. `literal()` values in queries against ENUM columns

When you build a sub-select that produces a static value compared against an enum column (e.g. a UNION ALL across `(material, "material")` / `(supply, "supply")` rows joined against `inventory_on_hand.entity_kind`), pass the enum type:

```python
literal(entity_kind, type_=INVENTORY_ENTITY_KIND_ENUM).label("entity_kind")
```

Without `type_=...` the literal renders as VARCHAR and PG refuses the implicit cast. (Bug + fix: [#63](https://github.com/bbengt1/voxel-ledger/pull/63) for `inventory_alerts.list_low_stock`.)

### Boolean defaults — adjacent gotcha

PG strict-types booleans the same way. Use `sa.false()` / `sa.true()`, never `sa.text("0")` / `sa.text("1")`. SQLite accepts integer literals; PG rejects them with `column "is_archived" is of type boolean but default expression is of type integer`. (Fixed across six migrations in [#49](https://github.com/bbengt1/voxel-ledger/pull/49).)

### Symptom: browser reports a CORS error

Two real bug rounds presented as CORS failures in the browser console. Both were 500-from-the-backend with no CORS headers attached (PG strict-typing errors out of the projection handler / service query). When a CORS error appears for a path that previously worked, **check the backend logs first** before chasing CORS config.

---

## Expected Change Pattern

- Backend feature work usually means updating: model or migration, event types + projection handler, schema, service, endpoint, and tests.
- Frontend feature work usually means updating: regenerated types, API hooks (TanStack Query), route/page state, form schema (zod), and loading/error handling.
- If a change touches sales, printers, inventory, or accounting, inspect existing tests first and extend them with the behavior change. Property tests are expected for BOM rollup, COGS FIFO, reference allocator, pieces-min, and depreciation schedules.

### Test-fixture patterns

Two setup patterns keep getting relearned by new tests. Steal them from existing tests instead of rolling your own each time.

- **Workshop location**: any test that exercises a material receipt or any inventory transaction needs an active `kind=workshop` `inventory_location` to land at. The receipt flow's default-receiving fallback (Phase 3.2) reads the `inventory.default_receiving_location_id` setting first, then falls back to the lowest-code active workshop. Without one, the receipt POST returns 400 with a clear configuration message. Centralizing fixture work is tracked in [#57](https://github.com/bbengt1/voxel-ledger/issues/57).
- **Open accounting period**: any test that posts a journal entry needs an open `accounting_period` covering the entry's `posted_at` date. Phase 4.3 wires the period-gating check before any other validation in `JournalEntriesService.post(...)`. The fix in every Phase 4 test is a 60-day window centered on today via `POST /api/v1/accounting/periods`. Tracked in the same spirit as #57 — worth a centralized fixture when fixture sprawl outgrows the inline pattern.

## Performance Budgets (must hold)

- API p95 (simple GET): < 200 ms
- List endpoints (≤ 500 rows): < 400 ms
- Cost-calc endpoint (`POST /jobs/calculate`): < 200 ms
- POS scan → line added: < 500 ms
- Printer status freshness from Moonraker: < 5 s
- Frontend FCP / TTI: < 1.5 s / 2.5 s
- Reports (≤ 1 year window): < 5 s

## Collaboration Notes

## Working Style
- Work is tracked and driven through GitHub issues. Prefer starting from an issue, implementing against that issue, and closing the loop in the issue or linked PR instead of treating chat alone as the source of truth.
- When creating or refining issues, use Plan mode and write a detailed, actionable user story. The body should include the user problem, scope, acceptance criteria, and concrete implementation guidance with examples across code, UI, data, and testing.
- Default to test-driven development when practical: outline the expected behavior first, add or update tests close to the change, then implement until the tests pass. If strict TDD is not practical for a slice, still add validation coverage before calling the work done.
- Every completed task should include explicit validation. Run the relevant commands, smoke tests, or manual verification steps and capture what was validated.
- Before marking work complete, update any impacted repository documentation so it stays accurate, detailed, and current. This includes specs under `print-sales-v2/`, README, `docs/`, runbooks, deployment notes, env docs, and feature-specific documentation whenever behavior or workflows change.
- Sub-agents may be used when they improve quality or speed, especially for bounded research, implementation, or testing work. Use them deliberately, keep scopes narrow, and integrate the results rather than duplicating effort.
- Collaboration tone should stay friendly, calm, and thorough. A little humor is welcome when it helps, but the work product should still be crisp, complete, and dependable.
- Personality: lean a little snarky and sarcastic in conversation — dry wit, light ribbing, the occasional eye-roll at obviously bad ideas. Punch up at problems, never at the user. The snark stays in chat; code, commits, PRs, issues, and docs remain professional and earnest.

## UX Laws For Frontend Work
- Treat UX laws as strong heuristics, not rigid commandments. When laws conflict, prioritize task clarity, accessibility, and operational speed.
- Aesthetic-Usability Effect: visual polish matters because users perceive polished interfaces as easier to use, but do not let attractive styling hide weak information architecture or broken flows.
- Doherty Threshold: acknowledge user actions within roughly `400ms` when practical. If real work will take longer, show immediate feedback with optimistic state changes, skeletons, spinners, or progress indicators.
- Fitts's Law: keep primary and frequent actions large, close, and easy to hit. Avoid tiny icon-only controls, especially in dense operational tables and mobile layouts.
- Hick's Law: reduce the number and complexity of choices shown at once. Prefer progressive disclosure, sensible defaults, recommended actions, and chunked workflows over dumping every option on screen.
- Jakob's Law: default to familiar interface patterns unless there is a strong product reason not to. Novel UI is acceptable only when it meaningfully improves the task and still provides clear cues.
- Law of Common Region, Law of Proximity, Law of Similarity, and Law of Uniform Connectedness: use spacing, containers, repeated styling, and visible connections to make relationships obvious. Do not rely on color alone to imply grouping.
- Law of Prägnanz: simplify layouts until the intended structure is obvious at a glance. Favor clean hierarchy, clear grouping, and low visual noise over decorative complexity.
- Miller's Law: chunk information so users do not have to hold too much in working memory. Do not treat `7 +/- 2` as a hard UI limit or as an excuse for arbitrary navigation/menu rules.
- Occam's Razor: prefer the simplest interaction model that still solves the real problem. Every new control, panel, filter, or modal should justify its existence.
- Pareto Principle: optimize the highest-frequency workflows and the biggest pain points first. The most used `20%` of the interface usually deserves the most design, testing, and polish attention.
- When proposing or reviewing frontend changes, name the relevant law or tradeoff when it helps explain why a design decision is better, faster, or easier to learn.
- Accessibility target for v2: WCAG 2.1 AA on primary flows (login, POS, job creation, invoice send, period close), with keyboard navigation for POS and job entry.

## Documentation UX And Freshness
- Treat documentation as a product surface. Docs should help readers orient quickly, build the right mental model, and find the authoritative answer without hunting through overlapping files.
- During the v2 rewrite, [`print-sales-v2/`](print-sales-v2/) is the authoritative spec set. Once Phase 0 lands, normal doc entry points re-emerge:
  - `README.md` is the repo-root orientation layer.
  - `docs/index.md` is the main audience and task-based documentation hub.
  - `docs/reference/index.md` is the authoritative technical reference map tied to the current codebase.
  - `docs/README.md` is only a compatibility pointer for older links and should not become a competing hub.
- Apply the UX laws to documentation structure (Hick, Jakob, Prägnanz, Miller, Occam, Pareto) — reduce competing entry points, use familiar patterns, chunk long content, optimize for the most common questions.
- Prefer editable visuals for relationship-heavy concepts: `mermaid` in markdown, source-controlled SVGs in `docs/assets/`. Avoid non-editable screenshots unless a real UI capture is the point.
- When behavior changes affect architecture, request flow, auth/session flow, deployment topology, feature-area maps, or workflow understanding, update the related diagrams and visual assets in the same change.
- Mark source-of-truth status clearly. Historical, contextual, or legacy-oriented docs should be labeled so readers do not mistake them for the maintained reference path. **The legacy v1 design docs are explicitly historical once v2 ships.**
- Keep major docs structurally consistent when practical: purpose/audience → quick summary → main content → validation/troubleshooting → related docs.
- Before calling documentation work complete: verify internal markdown links and asset references, review diagrams for accuracy against the current codebase, and confirm the docs still align with the intended IA and source-of-truth model.

## Commit & Pull Request Guidelines
- Commits: concise, present-tense summaries (e.g., `feat: add incident filter`, `fix: tighten auth middleware`). Group related changes.
- PRs: include context, linked ticket, and key commands run. Note API contract, route, feature-flag, or schema changes and update OpenAPI, docs, and UI consumers together. Attach screenshots or sample JSON for UI/endpoint changes; list env vars or workflow inputs touched. If documentation changed as part of the work, call that out explicitly in the PR summary.
- For v2 work, also note which implementation-plan phase the change belongs to and link the relevant `print-sales-v2/*` section.
