# Phase 4 — Feature-parity backlog

Priorities for the 16 feature-parity issues (#225–#240). Scored on
**cost × value × blockers**. Tier 1 ships first because each item is
small, used daily by bookkeepers, and has no upstream dependency.

> See [`CHANGELOG.md`](CHANGELOG.md) for shipped phases and
> [`docs/architecture.md`](docs/architecture.md) for the current
> bounded-context map.

## Tier 1 — Ship first (tiny + high frequency)
Each is one session, high daily-use value, no dependencies.

| Order | # | Title | Why first |
| - | - | --- | --- |
| 1 | [#226](https://github.com/bbengt1/voxel-ledger/issues/226) | **GL detail report** | Every month-end close needs it. Mirrors Trial Balance — one service file + one page. |
| 2 | [#231](https://github.com/bbengt1/voxel-ledger/issues/231) | **JE reversal** | Most common bookkeeper action; one service method + one button. |
| 3 | [#237](https://github.com/bbengt1/voxel-ledger/issues/237) | **Saved reports** | Used multiple times a day. Trivial CRUD; jsonb filter blob. |
| 4 | [#236](https://github.com/bbengt1/voxel-ledger/issues/236) | **Invoice write-off** | Replaces a 5-click manual JE with one button. |

## Tier 2 — High-value, medium-cost
Each is one or two sessions; unblocks downstream features.

| Order | # | Title | Why |
| - | - | --- | --- |
| 5 | [#229](https://github.com/bbengt1/voxel-ledger/issues/229) | **Per-division reporting** | Data already carries `division_id`; cheapest "unlock dead capability" play. |
| 6 | [#227](https://github.com/bbengt1/voxel-ledger/issues/227) | **Budget vs actual** | Phase 4.5 budgets are currently write-only — this report consumes them. |
| 7 | [#235](https://github.com/bbengt1/voxel-ledger/issues/235) | **Undeposited funds** | Foundational. Must land BEFORE #230 (bill-pay) and #234 (deposits) so money-movement uses the same clearing-account semantics. |
| 8 | [#240](https://github.com/bbengt1/voxel-ledger/issues/240) | **Recon discrepancy aging** | Surfaces hidden tech debt on day one. Small. |

## Tier 3 — Higher cost, broader surface
Wait for Tier 2 to stabilize the underlying surfaces.

| Order | # | Title | Why later |
| - | - | --- | --- |
| 9 | [#232](https://github.com/bbengt1/voxel-ledger/issues/232) | **Customer / vendor merge** | Owner-only destructive; needs careful per-table FK coverage. |
| 10 | [#230](https://github.com/bbengt1/voxel-ledger/issues/230) | **Bill-pay run UI** | Best after #235 lands so the disbursement clears through undeposited cleanly. |
| 11 | [#234](https://github.com/bbengt1/voxel-ledger/issues/234) | **Customer deposits** | Easier once #235 has established the liability-clearing pattern. |
| 12 | [#238](https://github.com/bbengt1/voxel-ledger/issues/238) | **Vendor statements** | Symmetric with customer statements — pattern is locked. |
| 13 | [#228](https://github.com/bbengt1/voxel-ledger/issues/228) | **Cash-basis toggle** | Touches every financial report's aggregation. Defer until the report stack is otherwise stable. |

## Tier 4 — Large strategic items
Each is a multi-PR effort.

| Order | # | Title | Why last |
| - | - | --- | --- |
| 14 | [#239](https://github.com/bbengt1/voxel-ledger/issues/239) | **Generalize reconciliation** | Refactor of stable code. Lower upside than greenfield items. |
| 15 | [#225](https://github.com/bbengt1/voxel-ledger/issues/225) | **Purchase orders** | New aggregate + receive lifecycle + UI. ~2-3 PRs. |
| 16 | [#233](https://github.com/bbengt1/voxel-ledger/issues/233) | **Project profitability** | New aggregate + `project_id` FK across half the schema + UI. ~3 PRs. |

## Working order

Take Tier 1 sequentially — each PR is small enough to land in one
session and the bookkeeper-noticeable wins compound: GL detail makes
month-end close 10x faster; saved reports make every recurring
report 1-click; write-off + JE reversal cover the most common
correction tasks.

After Tier 1, re-evaluate Tier 2 against actual usage. If month-end
close is the live pain point, #229 + #227 next. If reconciliation
gaps are surfacing, #235 + #240.
