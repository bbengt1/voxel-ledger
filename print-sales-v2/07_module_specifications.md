# 7. Module / Component Specifications

One section per major service. Each describes responsibilities, inputs/outputs, business logic, and error handling — described in plain English and pseudocode rather than current implementation specifics.

---

## 7.1 Cost Calculator

**Responsibility:** Given job inputs and current rates/settings, compute the full cost breakdown and recommended price. Pure function (no DB writes).

**Inputs:** material(s) × grams, plates × pieces, print hours, labor minutes, watts, packaging cost, shipping cost, margin override (optional), failure-buffer % (optional override).

**Outputs:** `{ electricity, material, labor, machine, packaging, shipping, subtotal, buffer, overhead, total_cost, cost_per_piece, price_per_piece, gross_margin_pct, gross_profit }`.

**Formula:**
```
electricity = (watts / 1000) * print_hours * settings.electricity_rate
material    = sum(grams_per_plate[i] * plates[i] * material.cost_per_g)
labor       = (labor_minutes / 60) * rate.labor_per_hour
machine     = print_hours * rate.machine_per_hour
subtotal    = electricity + material + labor + machine + packaging + shipping
buffer      = subtotal * (failure_rate_pct / 100)
overhead    = (subtotal + buffer) * (settings.overhead_pct / 100)
total_cost  = subtotal + buffer + overhead
pieces      = plate_strategy(plates)        # see below
cost_per_piece  = total_cost / pieces
margin_pct  = margin_override ?? settings.default_margin_pct
price_per_piece = cost_per_piece / (1 - margin_pct/100)
```

**Plate strategy:**
- Single-part plates: pieces = sum(qty per plate).
- Mixed plates (each plate has multiple parts): **pieces = min(parts) across plates** (a set is only complete when every part is printed). This was a deliberate fix in source (issue #399).

**Error handling:** All numeric inputs validated `>= 0`. Margin `< 1.0`. Division-by-zero guarded by minimum pieces = 1.

---

## 7.2 Inventory Service

**Responsibility:** Append-only ledger of stock movements; computes current on-hand; emits accounting postings.

**Operations:**
- `post(transaction)` — validates, persists, optionally posts a journal entry (production, sale, scrap).
- `on_hand(entity_kind, entity_id, location_id?)` — sums deltas.
- `transfer(from, to, qty)` — two paired transactions.
- `record_starting_balance(...)` — special transaction kind for go-live.

**Posting rules:**
| Kind | Inventory delta | Journal posting |
|---|---|---|
| `receipt` | + qty | Dr Inventory Asset / Cr AP or Cash |
| `production` | + qty for product, − qty for components | Dr Inventory (product) / Cr Inventory (components) at component cost |
| `sale` | − qty | (COGS posted by sales service) |
| `return` | + qty | Dr Inventory / Cr COGS |
| `adjustment` | ± qty | Dr/Cr Inventory / Cr/Dr Adjustment expense |
| `waste` / `scrap` | − qty | Dr Scrap expense / Cr Inventory |
| `transfer` | net zero | No JE |

**Idempotency:** Transactions are immutable; "void" is a new offsetting transaction referencing the original.

---

## 7.3 COGS FIFO Service

**Responsibility:** When a sale is confirmed, look up the FIFO unit cost of the products sold and emit the COGS posting.

**Algorithm:**
```
For each sale line:
  layers = inventory_layers(product_id) sorted by received_at asc, qty_remaining > 0
  qty_needed = line.qty
  cost_accum = 0
  for layer in layers:
    take = min(qty_needed, layer.qty_remaining)
    cost_accum += take * layer.unit_cost
    layer.qty_remaining -= take
    qty_needed -= take
    if qty_needed == 0: break
  if qty_needed > 0:
    cost_accum += qty_needed * fallback_unit_cost(product)  # last-known cost
  line.unit_cost = cost_accum / line.qty
```

**Persistence:** Layer consumption is recorded so refunds can restore.

---

## 7.4 Reference Number Service

**Responsibility:** Allocate human-friendly reference numbers (sale, invoice, quote, settlement). Must be race-safe across concurrent transactions.

**Pattern:** `{prefix}-{YYYY}-{NNNN}` (e.g., `S-2026-0042`, `INV-2026-0099`).

**Algorithm:** atomic `UPDATE reference_sequence SET next_value = next_value + 1 WHERE key = ? RETURNING next_value`. The `key` includes both prefix and year so sequences reset annually.

**Why this matters:** the original system generated `sale_number` from a yearly `COUNT(*)` which had a race condition under concurrent inserts. v2 MUST keep allocator-style sequence ownership.

---

## 7.5 Sales Service

**Responsibility:** Create/update/refund sales atomically. Compute totals. Trigger inventory + accounting postings.

**Create flow:**
1. Validate channel, customer (optional), payment method.
2. For each line: resolve product/job, snapshot unit_price.
3. Allocate `sale_number`.
4. Compute subtotal, fees (channel.platform_fee_pct + channel.fixed_fee), tax, total.
5. If status = confirmed: call cogs_fifo for each line; emit inventory transactions (sale); post journal entries (revenue, COGS, channel fees, tax payable, AR if invoice terms).
6. Save sale + items in single DB transaction.
7. Write audit log.

**Refund flow:**
1. Validate refund ≤ refundable balance.
2. If amount > approval threshold → create approval request, return 202.
3. On approval (or below threshold): reverse inventory transactions, reverse JEs, record refund amount, update status.

**Computed fields (denormalized for reporting):** subtotal, platform_fee, fixed_fee, tax, total, cogs, gross_profit, contribution_margin = gross_profit − platform_fees − shipping_cost.

---

## 7.6 POS Service

**Responsibility:** Optimize the in-person checkout path.

**Endpoints:**
- `POST /pos/scan/resolve` — input: barcode string. Output: product (active only). Tries UPC first, then internal SKU.
- `POST /pos/checkout` — input: lines, payment_method, optional customer. Output: created sale. Marks status=confirmed.

**Performance target:** < 500 ms scan-to-line-added including UI.

---

## 7.7 Printer Monitoring

**Responsibility:** Maintain persistent Moonraker websocket per active printer. Surface live state. Log history events.

**Lifecycle:**
- On app startup: for each `printer.is_active && moonraker_url`, open WS, subscribe to status/notify events.
- On printer create/update: open/close/restart WS as needed.
- On app shutdown: gracefully close all WS connections.
- On disconnect: exponential backoff reconnect.

**State exposed:** `idle | printing | paused | error`, current filename, progress %, ETA, temperatures.

**Hard requirement today:** the `websockets` Python lib must be installed; the monitor is imported at app startup, and the app fails to boot without it. v2 should lazy-import or feature-flag this.

---

## 7.8 Cost & Accounting Posting Helpers

**Accounting service** owns: chart of accounts, journal entry creation/voiding, period open/close, recurring JE expansion, depreciation/amortization runs, audit.

**Posting rules** for each business event are listed in [05 §5.4](05_data_model.md).

**Period-close invariant:** entries dated within a closed period are rejected unless they are explicit adjusting entries by an admin.

---

## 7.9 Settlement Reconciliation

**Responsibility:** Import marketplace payout statements; match to sales; post payout JE.

**Algorithm:**
1. Parse file → settlement_lines.
2. Auto-match by external order id or fuzzy on amount + date.
3. Operator manually matches the remainder.
4. Once fully matched: post JE — Dr Bank (payout), Cr Channel Receivable (gross sales already booked), Dr Channel Fees, Dr Refunds, etc.

---

## 7.10 Bank Reconciliation

**Responsibility:** Confirm book balance equals bank balance for a period; lock once balanced.

**Inputs:** account, period, imported statement lines, book entries (journal lines posted to that account in period).

**Operations:** mark lines cleared/uncleared; auto-clear via match rules; compute reconciliation diff; finalize.

---

## 7.11 Material Receipt Service

**Responsibility:** Record a purchase / arrival of filament. Update on-hand grams. Update weighted-average cost-per-gram. Post inventory asset JE.

**Weighted average:**
```
new_total_cost = old.on_hand_g * old.cost_per_g + receipt.qty_g * receipt.unit_cost
new_qty        = old.on_hand_g + receipt.qty_g
new_cost_per_g = new_total_cost / new_qty
```

---

## 7.12 Product BOM Service

**Responsibility:** CRUD BOM rows. Compute product unit cost from rolled-up BOM.

**Algorithm:**
```
unit_cost(product) =
    sum over BOM rows:
        row.qty * unit_cost(row.component)
```
- Material: `material.cost_per_g`
- Supply: `supply.cost_per_unit`
- Sub-product: recurse, with cycle detection.

---

## 7.13 Product Location Stock Service

**Responsibility:** Maintain a per-location stock view, derived from inventory_transactions.

**Strategy options:**
- Compute on demand (simple, slower).
- Maintain materialized rows updated by inventory_service (faster, more invariants to enforce).

Current implementation uses the materialized approach; v2 should consider an event-sourced view if performance is acceptable.

---

## 7.14 Reporting Service

**Responsibility:** Read-only aggregates over the ledger.

**Reports & SQL shapes:**
- **Inventory report:** `select product, on_hand, last_unit_cost, on_hand*last_unit_cost from product where not archived`.
- **Sales report:** group sale by `date_trunc(period, created_at)`, optionally by channel/payment_method.
- **P&L:** group journal_line by account.type in (revenue, expense), filtered by period.
- **Balance Sheet:** balances of asset/liability/equity accounts as of date.
- **Cash Flow:** indirect method derived from JEs.
- **Trial Balance:** sum debit/credit by account for period; total must equal.
- **AR aging:** open invoices bucketed by days overdue from `due_at`.
- **AP aging:** open bills similarly.
- **Sales tax liability:** sum tax-payable account by jurisdiction.

CSV exports use the same query, streamed.

---

## 7.15 AI Insights Service

**Responsibility:** Summarize recent activity (sales trends, low-margin SKUs, slow-mover stock). Background or on-demand.

**Inputs:** time window, scope. **Outputs:** natural-language summary + structured data for the dashboard.

---

## 7.16 Email Service

**Responsibility:** Send templated emails (quote, invoice, statement, password reset). Track delivery status.

**Operations:** `send(template, recipient, context, attachments?) -> delivery_id`. Retries on transient SMTP failure.

---

## 7.17 Attachment Service

**Responsibility:** Persist uploaded files with metadata; serve them back with auth check.

**Storage:** filesystem today; recommend object storage for v2.

---

## 7.18 Custom Field Service

**Responsibility:** Define and read/write custom fields on entities. Schema-on-read.

---

## 7.19 Batch Operations Service

**Responsibility:** Bulk archive/edit/delete with a preview step.

**Flow:** preview returns affected count + sample rows; commit applies inside a single transaction; audit-logged in bulk.

---

## 7.20 Approval Service

**Responsibility:** Gating workflow for refunds and adjustments above a threshold.

**State machine:** `pending → approved | rejected → applied | discarded`.

---

## 7.21 Audit Service

**Responsibility:** Record every accounting and high-risk mutation with user, before/after, timestamp. Queryable by entity.

---

## 7.22 Filament Resolver

**Responsibility:** Given an external print job's filament string (e.g., from a slicer or printer history), match to a `material` record by type+color+vendor heuristics.

---

## 7.23 Late Fee Service

**Responsibility:** On a schedule, find overdue invoices and post late-fee lines per terms.

---

## 7.24 Recurring Invoice / Expense / JE Services

**Responsibility:** On schedule (daily tick), expand any due templates into concrete invoices/bills/JEs and mark the next run.

---

## 7.25 Barcode / Product Barcode Service

**Responsibility:** Generate UPC/Code128/QR for a product; produce printable sheets.

---

## 7.26 Shipping Label Service (v2 — carrier-integrated)

**Responsibility:** Buy a real shipping label from a carrier aggregator (EasyPost or ShipStation), record the purchase, expose the label PDF, and apply inbound tracking updates.

**Operations:**
- `quote(sale, parcel, service?) -> rates[]` — fetch live rates.
- `buy(sale, parcel, rate_id) -> { tracking, label_url, cost }` — purchase, append `ShippingLabelPurchased` event, post shipping-expense JE, attach label as an `attachment`.
- `void(label_id)` — pre-use void/refund through the carrier; emits `ShippingLabelVoided`.
- `apply_tracking_update(event)` — invoked by the inbound carrier webhook; updates the sale tracking status.
- Static-label fallback retained for offline use (no carrier round-trip).

**Provider selection:** `SHIPPING_PROVIDER` env var (`easypost` or `shipstation`). Provider-specific adapter behind a single interface.

---

## 7.27 Note Service

**Responsibility:** CRUD freeform notes on polymorphic entities.

---

## 7.28 Merge Service

**Responsibility:** Merge two entity records (primarily customers): re-point FKs, archive loser, log decision.

---

## 7.29 Tax / Withholding Service

**Responsibility:** Apply tax profiles to invoice lines (compound and reverse-charge supported), record liabilities, support remittance recording.

---

## 7.30 Event Store + Projection Engine (new in v2)

**Responsibility:** Be the source of truth for all accounting-relevant state. Append events transactionally; apply projection updates in the same transaction; expose replay.

**Operations:**
- `append(events[]) -> positions[]` — atomic; assigns `position`, computes `prev_event_hash`, applies all registered projections in the same DB transaction.
- `replay(from_position?, types?)` — rebuild a projection from the log.
- `snapshot(aggregate)` — persist current state to skip future replay work.
- `subscribe(event_type, handler)` — register a projection or a side-effect (e.g. webhook dispatcher).

**Invariants:**
- One transaction per command: domain validation → event append → projection update → commit.
- Projections must be deterministic functions of the event stream.
- Period-close is itself an event; later events dated inside that period are rejected (unless preceded by an override event by `owner`).

## 7.31 Webhook Dispatcher (new in v2)

**Responsibility:** Deliver domain events to user-configured outbound URLs reliably.

**Operations:**
- Subscribes to event types from the event store; per matching event, enqueues a delivery job.
- Worker signs payload (HMAC-SHA256 with per-target secret), POSTs, records status.
- Retries with exponential backoff up to 24 h; dead-letters after.
- Exposes delivery history and manual retry via API.

## 7.32 OpenAPI → TS Codegen (new in v2)

**Responsibility:** Keep frontend types in lock-step with the backend contract.

**Operations:**
- Prebuild step: fetch OpenAPI spec from the backend (or read a checked-in snapshot), run `openapi-typescript` (or equivalent) to produce typed clients/hooks under `frontend/src/api/generated/`.
- CI: regenerate and fail if diff vs. committed output.
- Hand-maintained types are forbidden for resource bodies, params, and responses; presentation-only types may exist on top.

## 7.33 Settings Defaults

**Responsibility:** Provide safe defaults for every setting so a fresh install can compute prices and post journals immediately.
