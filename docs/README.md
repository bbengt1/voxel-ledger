# `docs/`

Runbooks, architecture diagrams, and reference material for Voxel Ledger / Print Sales v2.

## What lives here

This directory will fill in as Phase 0+ work lands:

- `deployment_n8n_workflow.md` — operator runbook for the canonical n8n deploy ([#9](https://github.com/bbengt1/voxel-ledger/issues/9)).
- `web01_runbook.md` — manual SSH path: where things live, how to tail logs, emergency restart, rollback ([#9](https://github.com/bbengt1/voxel-ledger/issues/9)).
- `openapi-codegen.md` — how the frontend type-generation contract works ([#5](https://github.com/bbengt1/voxel-ledger/issues/5)).
- `index.md` — task-based documentation hub (once there's enough to organize).
- `reference/` — authoritative technical reference tied to the codebase.
- `assets/` — mermaid sources and SVGs for diagrams.

## Source-of-truth model

Until Phase 0 lands, the authoritative specs live under [`../print-sales-v2/`](../print-sales-v2/). Once code exists, this directory becomes the home for runbooks and reference material that tracks the actual implementation.

[`../print-sales-v2/`](../print-sales-v2/) will then be marked as the historical design record — readers should not mistake design specs for the maintained reference path.

## Related

- [`../print-sales-v2/IMPLEMENTATION_PLAN.md`](../print-sales-v2/IMPLEMENTATION_PLAN.md) — phased roadmap.
- [`../agents.md`](../agents.md) — documentation UX rules and freshness expectations.
