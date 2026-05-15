# `frontend/`

React 19 + Vite + TypeScript SPA for the Voxel Ledger / Print Sales v2 rewrite.

## Status

The full bounded-context UIs through Phase 4 are live: login + protected-route shell, theme toggle, admin (users, custom fields), catalog (materials/supplies/rates/products with BOM tab, notes + attachments sections), inventory (locations/transactions/alerts/starting balances), and accounting (COA tree/journal composer with live debit-credit math/period management/approvals queue with type-aware payload renderer/divisions/budgets with variance). Phase 5 production UI is filed but not landed.

148 vitest tests / 41 test files on the latest main.

## Stack

- **React 19** + **TypeScript** (strict mode, including `noUncheckedIndexedAccess`).
- **Vite** for dev server and build.
- **Tailwind 4** + **Radix UI** primitives (thin wrappers in `src/components/ui/`).
- **TanStack Query 5** for server state.
- **Zustand 5** for client state (auth store with persisted localStorage).
- **react-hook-form** + **zod** for forms and validation.
- **axios** with JWT bearer + refresh-rotation interceptor (single in-flight refresh under burst).
- **recharts** for dashboard charts (Phase 10).
- **marked** + **dompurify** for safe markdown rendering (notes section).
- **Vitest** + **@testing-library/react** for unit/component tests.

## Layout

- `src/api/`
  - `client.ts` — the shared axios instance with auth + 401-refresh-and-retry interceptor. `baseURL` is **origin only**; every call site provides the full path including `/api/v1/`.
  - `types.ts` and `openapi.json` — **generated** from the backend OpenAPI spec. Do not hand-edit. CI fails on drift via `pnpm run codegen:check`. See [`../docs/openapi-codegen.md`](../docs/openapi-codegen.md).
  - `typed.ts` — typed thin wrapper around axios that constrains URLs to `keyof paths`. For paths with query strings or interpolated `${id}` templates that aren't in `paths`, fall back to raw `apiClient` (this is a known gap — see UserDetail and CustomFields for the pattern).
- `src/components/`
  - `ui/` — Radix wrappers (Button, Input, Dialog, Tooltip, DropdownMenu).
  - `layout/` — AppShell, Sidebar, TopBar, Breadcrumbs.
  - `auth/` — `<RequireAuth>` route guard.
  - `theme/` — theme provider (dark/light/system, persisted).
  - per-context component folders (`admin/`, `catalog/`, `inventory/`, `accounting/`, `platform/`, `approvals/`) for shared section components like `<OnHandSection>`, `<NotesSection>`, `<AccountPicker>`, `<JournalLineGrid>`.
- `src/pages/` — route-level UI grouped by bounded context.
- `src/store/` — Zustand stores (`useAuthStore` is the only one today).
- `src/lib/` — small utilities (e.g. `markdown.ts`).

## Conventions

- API types are generated from `/api/v1/openapi.json` at `pnpm prebuild`. CI fails on drift. Don't hand-edit.
- baseURL is the origin; every call site passes the full `/api/v1/...` path. See `apiClient` in `src/api/client.ts` for the rationale.
- No business logic in components. Hooks and services own that.
- Forms use react-hook-form + zod; the shared `<Form>` wrapper bridges them.
- WCAG 2.1 AA on primary flows (login, POS-equivalents, job entry). Keyboard-first where feasible.

## Quick commands

```bash
pnpm install                                # from repo root
pnpm --filter @voxel-ledger/frontend dev    # Vite dev server on 5173
pnpm test -- --run                          # vitest one-shot
pnpm exec tsc --noEmit                      # type-check
pnpm exec eslint .                          # lint
pnpm run codegen:check                      # regenerate + git diff check
```

The repo-root `make bootstrap` handles everything for first-run setup.

## Related

- [`../docs/development.md`](../docs/development.md) — full dev loop.
- [`../docs/architecture.md`](../docs/architecture.md) — current implementation map.
- [`../docs/openapi-codegen.md`](../docs/openapi-codegen.md) — type-generation contract.
- [`../print-sales-v2/08_ui_ux.md`](../print-sales-v2/08_ui_ux.md) — UI/UX spec (historical design).
- [`../agents.md`](../agents.md) — collaboration rules + UX laws.
