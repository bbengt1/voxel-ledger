# OpenAPI → TypeScript codegen

> Status: source of truth. Owns the contract between backend and frontend.
> Phase 0.5 deliverable (issue [#5](https://github.com/bbengt1/voxel-ledger/issues/5)).

## TL;DR

- The backend's FastAPI spec at `/api/v1/openapi.json` is the **single source
  of truth** for API shapes.
- `frontend/src/api/openapi.json` is a committed copy of that spec.
- `frontend/src/api/types.ts` is generated from it by `openapi-typescript`.
- Both files are **generated artifacts**. Do not hand-edit either. The
  `.gitattributes` flags them as `linguist-generated=true` so GitHub treats
  them accordingly.
- CI runs `pnpm run codegen:check` and fails the build if anything drifts.

## Audience

Anyone changing a FastAPI schema, router signature, or response shape. If
your change touches `backend/app/api/` or `backend/app/schemas/` you almost
certainly need to regenerate.

## The contract

1. Backend changes a schema or endpoint.
2. Author runs `pnpm run codegen:export && pnpm run codegen`.
3. Both `openapi.json` and `types.ts` get committed alongside the backend
   change in the same PR.
4. Frontend code consumes the generated types via `@/api/typed`.
5. CI re-runs the export and codegen on every PR and aborts the build if
   the committed artifacts differ from what the current backend produces.

There is no out-of-band "regenerate later" — the spec, the types, and the
backend code travel together.

## How to regenerate locally

From the repo root:

```sh
# 1. Re-export the spec from the backend code, then regenerate types.
pnpm run codegen:export   # writes frontend/src/api/openapi.json
pnpm run codegen          # writes frontend/src/api/types.ts

# Equivalent one-shot that also asserts cleanliness:
pnpm run codegen:check
```

`codegen:export` shells into `python -m scripts.export_openapi`. It needs
the backend Python dependencies importable — i.e. either run from a venv
where `pip install -e backend[dev]` has been done, or rely on the CI image
that already has them. Importing the FastAPI app does not require a running
database; the script never enters the lifespan.

`codegen` only reads the committed `openapi.json` — it does NOT contact the
backend. That's intentional: it lets `pnpm build` work offline and keeps
`prebuild` cheap.

## Determinism

`scripts/export_openapi.py` writes the spec with `sort_keys=True`,
`indent=2`, `ensure_ascii=False`, and a trailing newline. Two consecutive
runs produce byte-identical output. The codegen wrapper at
`frontend/scripts/codegen.mjs` normalizes line endings on the generated
`types.ts` for the same reason. If you see flapping diffs, that's a bug —
file an issue.

## When CI flags drift

You'll see a failure on `pnpm run codegen:check` with a `git diff` showing
the mismatch. To fix locally:

```sh
pnpm run codegen:check
# Inspect the diff. If it reflects an intentional backend change, commit
# the regenerated files. If it doesn't, you probably forgot to regenerate
# after a backend change.
git add frontend/src/api/openapi.json frontend/src/api/types.ts
git commit -m "chore: regenerate openapi types"
```

If the diff is large and surprising, look for:

- A FastAPI schema edit you didn't realize was wire-visible.
- A new dependency that changed how FastAPI emits its spec (e.g. a Pydantic
  upgrade reordering keys).
- A non-deterministic detail leaking into the spec (e.g. an `Annotated`
  type generating a fresh ref name on every import). These are bugs in the
  backend code, not the codegen pipeline — fix them at the source.

## Using the generated types from the frontend

The thin typed wrapper lives in `frontend/src/api/typed.ts`:

```ts
import { api } from "@/api/typed";

// Response is typed against the FastAPI schema for `/api/v1/auth/me`.
const me = await api.get("/api/v1/auth/me");

// Request body is constrained to the spec.
const session = await api.post("/api/v1/auth/login", {
  email: "owner@example.com",
  password: "...",
});
```

The wrapper composes with the existing axios instance from `client.ts`, so
the JWT injection, 401 redirect, and base URL handling all still apply.

## Versioning and breaking changes

There is no formal API version bumping yet. When the spec changes in a
backwards-incompatible way (renamed field, removed endpoint, changed
status code), call it out explicitly in the PR description. We'll codify
a migration-note process once we have real consumers outside the monorepo.

## Limits and escape hatches

The typed wrapper currently covers JSON request/response bodies for the
five standard HTTP methods. It does NOT yet model:

- Multipart/form uploads (`Form`, `File` in FastAPI). For those, import
  `apiClient` directly from `@/api/client` and accept that you're outside
  the type-safe path.
- Path parameter interpolation. Today you build the URL with a template
  literal; the generated `paths` keys are templated (`"/api/v1/x/{id}"`),
  and a small helper will land once we have a real parameterized route.

## Files you'll touch

| Path | Purpose |
| --- | --- |
| `backend/app/main.py` | Sets `openapi_url="/api/v1/openapi.json"`. |
| `scripts/export_openapi.py` | Deterministic spec exporter. |
| `frontend/scripts/codegen.mjs` | Codegen wrapper (adds header, normalizes EOL). |
| `frontend/package.json` | `codegen`, `codegen:export`, `codegen:check`, `prebuild`. |
| `frontend/src/api/openapi.json` | Generated. Committed. |
| `frontend/src/api/types.ts` | Generated. Committed. |
| `frontend/src/api/typed.ts` | Typed adapter, hand-written. |
| `frontend/src/api/client.ts` | Axios instance, hand-written. |
| `.gitattributes` | Marks the two generated files as such. |

## Related

- [`agents.md`](../agents.md) — the "no hand-typed resource shapes" rule.
- [`print-sales-v2/IMPLEMENTATION_PLAN.md`](../print-sales-v2/IMPLEMENTATION_PLAN.md) §4.6, §5 Phase 0.
- [`print-sales-v2/12_glossary_assumptions_decisions.md`](../print-sales-v2/12_glossary_assumptions_decisions.md) — codegen decision record.
