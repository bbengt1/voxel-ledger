# `docs/`

Runbooks, architecture reference, and operator-facing documentation for Voxel Ledger / Print Sales v2.

## Index

### Architecture & reference

- [`architecture.md`](architecture.md) — current implementation map. Bounded contexts, projections, key data flows. The "what landed" companion to [`../print-sales-v2/04_architecture.md`](../print-sales-v2/04_architecture.md) (which is now historical design).
- [`event_catalog.md`](event_catalog.md) — every event type in the system, organized by aggregate. Payload schemas, emitters, subscribers. The source of truth for the event-sourced parts of the codebase.
- [`migrations.md`](migrations.md) — reverse-chronological migration changelog. What each migration does, what it depends on, any operator gotchas.

### Development

- [`development.md`](development.md) — first-clone to working stack walkthrough.
- [`openapi-codegen.md`](openapi-codegen.md) — frontend type-generation contract.

### Deployment & operations

- [`deployment_n8n_workflow.md`](deployment_n8n_workflow.md) — canonical n8n deploy workflow runbook.
- [`web01_runbook.md`](web01_runbook.md) — manual SSH ops path.

## Source-of-truth model

- This directory tracks **what's implemented**.
- [`../print-sales-v2/`](../print-sales-v2/) holds the **original design specs** — historical, not maintained. Useful for "why did we decide X" archaeology, not for "what does X do today."
- [`../agents.md`](../agents.md) is the collaboration guide. PG strict-typing patterns + test fixture conventions live there.

## Conventions

- Markdown only. Tables where they help; bullets where they don't.
- Cross-link liberally between docs. File paths in backticks.
- When a behavior changes, update the relevant doc in the same PR. CI doesn't enforce this; reviewers should call it out.
- Diagrams use Mermaid (renders on GitHub) or source-controlled SVGs under `assets/`. No screenshots unless a real UI capture is the point.

## Related

- [`../print-sales-v2/IMPLEMENTATION_PLAN.md`](../print-sales-v2/IMPLEMENTATION_PLAN.md) — phased roadmap (the original plan; still useful for sequencing context).
- [`../README.md`](../README.md) — repo-root orientation.
