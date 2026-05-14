# 12. Glossary, Assumptions, and Decisions

## 12.1 Glossary

| Term | Definition |
|---|---|
| **BOM** | Bill of Materials. The list of materials, supplies, and sub-products that compose a product. |
| **Buffer (failure buffer)** | A percentage added to subtotal to account for failed prints. |
| **Channel** | A sales platform (Etsy, Amazon, Direct, In-Person). Carries platform fee % and fixed fee per order. |
| **Chart of Accounts (COA)** | The list of accounting accounts (asset/liability/equity/revenue/expense). |
| **Contribution margin** | Gross profit minus channel fees and shipping cost. |
| **COGS** | Cost of Goods Sold. The unit cost of products sold in a period. |
| **Cost engine** | The server-side calculator that turns job inputs into total cost and price. |
| **Division** | A reporting segment that tags journal lines. |
| **FIFO** | First-In-First-Out — the inventory cost-flow assumption used at sale time. |
| **Filament** | Spooled plastic feedstock for printers; tracked as a `material`. |
| **Fixed fee** | Per-order flat fee charged by a channel, independent of order amount. |
| **G-code** | Machine instructions consumed by the printer; produced by a slicer. The app does not generate G-code. |
| **Job** | A planned or in-flight print run with a cost breakdown. |
| **Kit** | A product whose BOM contains other products. |
| **Klipper / Moonraker** | Open-source printer firmware (Klipper) + API server (Moonraker) used for printer integration. |
| **Margin** | The percentage of price that is profit. `price = cost / (1 - margin)`. |
| **Material** | Filament inventory item (PLA/PETG/TPU/ABS/PLA+/other) with cost-per-gram. |
| **Moonraker** | See Klipper / Moonraker. |
| **Overhead** | A percentage added to (subtotal + buffer) to cover indirect costs. |
| **Plate** | A single print bed run inside a job; may include multiple parts. |
| **POS** | Point of Sale — in-person checkout with barcode scanning. |
| **Production order** | A queue of jobs to be run, often across multiple printers. |
| **Rate** | An hourly value: labor rate (per hour) or machine rate (per hour). |
| **Receipt** (material receipt) | A stock-in event for filament; updates on-hand and weighted-average cost. |
| **Reference number** | A human-friendly identifier like `S-2026-0042` allocated race-safely. |
| **Reference number allocator** | The service that hands out reference numbers using DB sequences. |
| **Settlement** | A marketplace payout statement that reconciles gross sales − fees − refunds = payout. |
| **Slicer** | Software that turns a 3D model into G-code (not part of this app). |
| **SKU** | Stock-Keeping Unit. Auto-generated unique product identifier. |
| **Supply** | Non-filament consumable (magnets, screws, LEDs, inserts, adhesives, etc.). |
| **UPC** | Universal Product Code; an optional external barcode on a product. |
| **Weighted-average cost** | Inventory valuation method that updates unit cost on receipt based on combined value/qty. |
| **WS** | WebSocket. |

## 12.2 Assumptions Made During This Documentation

1. The source repo at the documented snapshot reflects current behavior; some flows were inferred from naming, repo memory, and `agents.md` rather than executed.
2. USD is the only currency (confirmed by project memory).
3. Single-tenant deployment (single business, single org).
4. Admin/non-admin is the only role distinction in production today.
5. Approval thresholds are configurable but specific values were not enumerated here.
6. Reference numbering format is `{PREFIX}-{YYYY}-{NNNN}`, with `S` for sales, `INV` for invoices, etc.
7. Cameras are 1:1 with printers (per source schema).
8. Mixed-plate pieces formula is `min(parts)` (per source fix history).
9. PostgreSQL 16 is the production target; SQLite is dev/test only.
10. The Moonraker integration is required and not optional at runtime.

Any assumption that proves wrong should be corrected here before v2 implementation depends on it.

## 12.3 Key Design Decisions (with rationale)

| Decision | Rationale | Trade-off |
|---|---|---|
| **Service-layer business logic** | Keep routers and components thin so the same logic can be tested and reused | Some indirection vs. inline code |
| **Append-only inventory ledger** | Auditability and FIFO correctness | More rows; corrections must be new transactions |
| **Race-safe reference allocator via DB sequence** | Real incident with COUNT-based numbering caused collisions | Adds a row-locking dependency at sale time |
| **USD-only** | YAGNI for FX; closed as won't-do twice (#256, #319) | Locks out future i18n until revisited |
| **Single global settings store** | Single-tenant simplicity | Would need rework to become per-org/per-user |
| **Polymorphic refs** (entity_kind + entity_id on transactions/attachments/notes/audit) | Simpler than N FK tables for cross-cutting concerns | Loss of strict referential integrity at DB level |
| **JWT bearer auth, no refresh** | Smallest viable auth | No silent renewal; users get bounced more often |
| **Inline background work** | Avoid operating a worker queue for a small business | Long-running tasks block request handlers; harder to retry |
| **Moonraker WS at startup** | Real-time printer state is core to the operator experience | Hard startup dependency on `websockets` lib |
| **Tailwind + Radix on the frontend** | Fast operator UI, accessible primitives | More component code than a heavy library |
| **PostgreSQL only in prod** | Real DB matters for the accounting ledger | Slower local setup than SQLite-everywhere |
| **Migrations enforced on every deploy** | Avoid the 2026-05-09 startup-crash incident | Slightly slower deploys |
| **Single deploy workflow (n8n)** | Observable, repeatable | One more tool to maintain |

## 12.4 Known Technical Debt / Hacks in v1

- ~65 models, ~60 endpoint modules, ~45 service modules — boundaries between Sales / Accounting / Inventory blur. A v2 should formalize bounded contexts.
- Some accounting subsystems lack tests; others (sales, ref numbering, BOM) are well covered.
- `printer_monitoring` import at startup makes the `websockets` lib a hard dep for tests too.
- Materialized per-location stock relies on correct ledger writes; invariants are enforced by code, not the DB.
- Docs are extensive (~70 markdown files) but feature-shaped, hurting discoverability.
- Some endpoint paths have legacy aliases (e.g., `/sales-channels` vs `/sales/channels`).
- Frontend types are hand-maintained per-feature; drift between server schema and client types is a recurring source of bugs.
- Background work (recurring invoices, depreciation, late fees, AI insights) is inlined; needs to move to a worker.
- No staging environment — production is the only deployed environment.
- `kit_component` overlaps with `product_bom_item`; consolidate in v2.

## 12.5 Out-of-Scope (explicit)

- Multi-currency / FX.
- Multi-tenant / SaaS.
- Card processing / PCI scope.
- Public customer portal.
- Native mobile apps.
- Slicer / G-code generation.

## 12.6 v2 Decisions (resolved)

| # | Question | Decision | Implication |
|---|---|---|---|
| 1 | Role/permission model | **RBAC** | Define a small set of named roles (e.g. `owner`, `bookkeeper`, `production`, `sales`, `viewer`). Each role maps to a permission set. Deny-by-default. Replace today's single `is_admin` boolean. |
| 2 | Accounting ledger style | **Event-sourced** | Domain events (e.g. `SaleConfirmed`, `RefundIssued`, `MaterialReceived`, `JournalAdjusted`) are the source of truth. Journal lines + account balances + reports become projections rebuilt from the event log. See [§12.6.1](#1261-event-sourced-accounting-architecture-notes). |
| 3 | Frontend TS types from OpenAPI | **Yes** | Add `openapi-typescript` (or equivalent) to the frontend build. Generated client + types live under `frontend/src/api/generated/`. Backend OpenAPI spec is the contract; no hand-typed shapes for resource bodies. |
| 4 | Background job queue | **Open** — defer to implementation. PG-native (pg-boss / pgmq / Arq with Redis) preferred over heavy options. | Recurring invoices, depreciation runs, settlement imports, late fees, AI insights, and event-projection rebuilds run on the worker. |
| 5 | Staging environment | **No** | Single environment (`web01`). All testing happens locally before deploying. Migrations and seed data must remain safe-to-rerun. |
| 6 | Attachment storage | **Local disk** | Keep `/srv/3d-print-sales/data/attachments`. No S3 abstraction in v1 of v2. Nightly rsync to offsite stays the backup story. |
| 7 | Auth additions | **Refresh tokens only** | Short access tokens (~15 min) + long refresh tokens (~30 days, rotating, revocable on password change). No MFA, no SSO in v2. |
| 8 | Webhook surface | **Yes — both directions** | Outbound: user-configured destinations for events (sale.created, invoice.paid, printer.failed, settlement.imported). Inbound: per-channel webhook endpoints to replace marketplace file imports where APIs allow. |
| 9 | Carrier-integrated shipping | **Yes** | Integrate one carrier aggregator (EasyPost or ShipStation — pick one). Shipping label endpoint becomes a carrier-backed buy-label call. Static-label fallback remains for offline use. |
| 10 | Consolidate `kit_component` | **Yes** | Drop `kit_component`. A kit is a product whose BOM contains `product` components. Single `product_bom_item` table, polymorphic component (`material` \| `supply` \| `product`). Cycle detection required. |

### 12.6.1 Event-sourced accounting — architecture notes

The append-only journal stays as the canonical *projection* of accounting state, but it is no longer the source of truth. The source of truth is the **domain event log** — an immutable, append-only table of business events with a monotonically increasing position.

```mermaid
flowchart LR
  subgraph Command
    UI[User action / API call] --> H[Command handler]
    H --> AGG[Domain aggregate<br/>validates invariants]
    AGG --> EVT[Append event(s)<br/>to event log]
  end

  EVT --> BUS[(Event log<br/>append-only)]

  subgraph Projections
    BUS --> JE[Journal projection<br/>journal_entry + journal_line]
    BUS --> BAL[Account balance projection]
    BUS --> INV[Inventory ledger projection]
    BUS --> AR[AR / AP projections]
    BUS --> RPT[Report cubes<br/>P&L, BS, CF, TB]
  end
```

**Invariants and rules:**
- Events are immutable. Corrections are new events (e.g. `RefundIssued`, `JournalAdjusted`), never edits.
- Each event carries: `id` (uuid), `position` (monotonic int8), `type`, `aggregate_id`, `payload` (jsonb), `occurred_at`, `actor_user_id`, `correlation_id`, `causation_id`, `schema_version`.
- Projections are rebuildable from the event log alone. A "rebuild" command should produce identical projections.
- Period close is itself an event (`PeriodClosed`); attempts to post events dated within a closed period emit a `PostingRejected` event unless an admin's override event precedes them.
- Reference-number allocator stays separate (DB sequence) so allocations are race-safe even before the event is appended.
- Snapshots (per aggregate, every N events) keep replay fast.
- Audit log is derived directly from the event log; the separate `audit_log` table becomes a projection (or is dropped).
- Hash-chain (`prev_event_hash` per event) gives tamper-evidence; cheap and high-value for an accounting system.

**Migration from v1:**
- Replay v1 state into a synthetic seed of events: `MaterialReceived`, `JobCompleted`, `SaleConfirmed`, `InvoiceIssued`, `PaymentReceived`, `JournalEntryPosted` (manual JEs), `PeriodClosed`. Run projections; verify balances match v1 reports. Lock cutover.

**Trade-offs:**
- More machinery up front. The payoff is auditability, rebuildable reports, easy fan-out (webhooks ride the event log), and a clean substrate for the inbound/outbound webhook surface in question #8.
- Requires a versioned event schema discipline (`schema_version` per event type) and an explicit upcaster pattern for old events.

