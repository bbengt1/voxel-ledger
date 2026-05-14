# Contributing

Welcome. This file is the operational README — how to get your environment
running, how to run the same checks CI runs, and how to open a PR that won't
bounce. For collaboration norms and the architectural non-negotiables (the
codegen-drift contract, in particular), read `agents.md`. For the phased
roadmap, see `print-sales-v2/IMPLEMENTATION_PLAN.md`.

## Prereqs

- Python 3.12+
- Node 20.11+ and pnpm 9 (`corepack enable` will pin the version declared in
  `package.json` automatically)
- Docker (only required for integration tests that opt into a real Postgres)
- `pre-commit` (`pip install pre-commit`)

## First-time setup

The one-command bootstrap brings up the full stack (Postgres, backend with
hot reload, frontend with HMR), runs migrations, and seeds the owner user:

```bash
git clone git@github.com:bbengt1/voxel-ledger.git
cd voxel-ledger
make bootstrap
pre-commit install   # mirrors CI hooks
```

See [`docs/development.md`](docs/development.md) for what `make bootstrap`
does, the dev loop (hot reload, HMR, codegen after schema changes), common
failure modes, and clean reset.

## Dev loop

The short version: `make dev` brings the stack up and tails logs;
`make down` stops it; `make nuke` wipes containers and volumes (prompts).
The long version is in [`docs/development.md`](docs/development.md).

## Tests

```bash
# Backend unit tests (in-memory SQLite — fast, no Docker required)
pytest backend/tests -q

# Frontend (vitest, single-shot)
pnpm --filter @voxel-ledger/frontend test
```

Integration tests marked with `@pytest.mark.integration` spin up a real
Postgres via testcontainers and need Docker running.

## Before pushing

Run the same gates CI runs. The pre-commit hooks cover most of it.

```bash
pre-commit run --all-files          # ruff, prettier, eslint, basic hygiene
pytest backend/tests -q             # backend tests
pnpm --filter @voxel-ledger/frontend exec tsc --noEmit
pnpm --filter @voxel-ledger/frontend test
pnpm --filter @voxel-ledger/frontend build
```

If your change touches any backend Pydantic schema, FastAPI route, or
response model, you **must** re-run codegen so the generated TS contract
stays in sync. CI enforces this with a drift check:

```bash
pnpm run codegen                    # regenerate spec + types
pnpm run codegen:check              # what CI runs — diffs against HEAD
```

If `codegen:check` reports a diff, commit the regenerated
`frontend/src/api/openapi.json` and `frontend/src/api/types.ts` along with
the backend change. See `docs/openapi-codegen.md` for the contract.

## Pull requests

- Title: terse, present-tense, mention the phase if v2 work (e.g.
  `Phase 0.6: CI pipeline`).
- Body sections (per `agents.md`):
  - **Summary** — what changed, why.
  - **Decisions worth flagging** — anything reviewers should push back on.
  - **Test plan** — exact commands you ran and their outcome.
  - **Spec references** — `print-sales-v2/*` sections and the GitHub issue
    (`Closes #N`).
- Link the issue. List the commands you ran. Call out env vars or workflow
  changes. Attach screenshots for UI work.
- Use squash-merge. Keep history linear.

## Pointers

- `agents.md` — collaboration rules, codegen-drift contract, security
  guardrails.
- `print-sales-v2/IMPLEMENTATION_PLAN.md` — phased roadmap.
- `print-sales-v2/10_testing.md` — testing strategy.
- `docs/openapi-codegen.md` — how the spec/type-generation pipeline works
  and why drift is a hard error in CI.
