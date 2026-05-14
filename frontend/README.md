# `frontend/`

React 19 + Vite + TypeScript SPA for the Voxel Ledger / Print Sales v2 rewrite.

## Stack

- **React 19** + **TypeScript** (strict mode).
- **Vite** for dev server and build.
- **Tailwind 4** + **Radix UI** primitives.
- **TanStack Query 5** for server state.
- **Zustand 5** for client state (auth, POS cart).
- **react-hook-form** + **zod** for forms and validation.
- **axios** with JWT bearer + 401-redirect-preserving-URL interceptor.
- **recharts** for dashboard charts (Phase 10).
- **Vitest** for unit tests; Playwright for the small end-to-end suite.

## What lives here

The skeleton lands in [#4](https://github.com/bbengt1/voxel-ledger/issues/4). Until then, this directory is intentionally empty.

When it exists, layout will be roughly:

- `src/api/` — generated OpenAPI types + thin typed client. **Do not hand-edit.**
- `src/components/` — layout, shared UI, Radix wrappers.
- `src/pages/` — route-level UI, grouped by bounded context.
- `src/store/` — Zustand stores.
- `src/lib/` — small utilities only.

## Conventions

- API types are generated from `/api/v1/openapi.json` at prebuild — see [#5](https://github.com/bbengt1/voxel-ledger/issues/5). CI fails on drift.
- No business logic in components. Hooks and services own that.
- WCAG 2.1 AA on primary flows. Keyboard-first for POS and job entry.

## Related

- [`../print-sales-v2/08_ui_ux.md`](../print-sales-v2/08_ui_ux.md) — UI/UX spec.
- [`../print-sales-v2/IMPLEMENTATION_PLAN.md`](../print-sales-v2/IMPLEMENTATION_PLAN.md) — phased roadmap.
- [`../agents.md`](../agents.md) — collaboration rules and UX laws.
