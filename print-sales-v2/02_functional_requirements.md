# 2. Functional Requirements Specification

This is the master list of features, organized by domain. Each domain has: purpose, key use cases, primary inputs/outputs, and business rules. Implementation specifics are in [07_module_specifications.md](07_module_specifications.md).

---

## 2.1 Authentication & User Management

**Purpose:** Gate access to the system; identify the user for audit logging.

**Use cases:**
- UC-AUTH-1: User logs in with email/password → receives JWT, frontend persists session.
- UC-AUTH-2: User updates own password (must supply current).
- UC-AUTH-3: Admin registers new user, sets active/inactive, changes password, deletes user.
- UC-AUTH-4: Session expires or token rejected → user redirected to login, original URL preserved.

**Business rules:**
- Passwords hashed with bcrypt; never stored plaintext.
- Admin flag is a single boolean today; v2 should generalize to a role/permission model.
- One seeded admin from env (`ADMIN_EMAIL` / `ADMIN_PASSWORD`); seed refuses to run with tracked placeholder secrets.

---

## 2.2 Settings & Configuration

**Purpose:** Business-wide tunables consumed by the cost engine and UI.

**Use cases:**
- UC-SET-1: Admin views and edits settings (currency, default margin %, electricity rate, default printer watts, default packaging cost, default shipping cost, failure-buffer %, overhead %, platform-fee defaults).
- UC-SET-2: Admin updates a single setting by key.
- UC-SET-3: Admin updates multiple settings in one request (bulk).

**Business rules:**
- All cost-engine inputs must have safe defaults so a fresh install can compute prices immediately.
- Currency is USD (no FX conversion supported).
- Settings are global (single-tenant assumption).

---

## 2.3 Materials (Filament Inventory)

**Purpose:** Track filament spools, cost-per-gram, on-hand grams, by color and material type.

**Use cases:**
- UC-MAT-1: CRUD a material (name, type [PLA/PETG/TPU/ABS/PLA+/other], color, cost-per-gram, on-hand grams, vendor, notes).
- UC-MAT-2: List active vs. archived; search by name/color.
- UC-MAT-3: Record a material receipt (adds grams, may update weighted-average cost).
- UC-MAT-4: Be consumed by a job/plate, decrementing on-hand grams.

**Business rules:**
- Cost-per-gram is the unit cost used in the cost engine.
- Material receipts can change weighted-average cost (see [Material Receipts Valuation](../docs/material_receipts_valuation.md) in source).
- Negative stock is allowed but flagged; a material below a configurable threshold raises a low-stock alert.

---

## 2.4 Supplies (Non-Filament Consumables)

**Purpose:** Track non-filament purchased items used in products (magnets, screws, LEDs, inserts, wiring, adhesives, packaging consumables).

**Use cases:**
- UC-SUP-1: CRUD a supply (name, category, unit, cost per unit, on-hand qty, reorder point, vendor).
- UC-SUP-2: Adjust quantity (with reason).
- UC-SUP-3: Be referenced as a BOM component on a product.

**Business rules:**
- Same valuation conventions as materials (weighted-average cost on receipt; configurable later).
- Supplies feed product BOM cost rollups.

---

## 2.5 Rates

**Purpose:** Labor rate (per hour), machine rate (per hour), overhead percentage. Used by cost engine.

**Use cases:**
- UC-RATE-1: CRUD rates; mark active/inactive.
- UC-RATE-2: Default labor and machine rate are picked up automatically by the cost engine.

**Business rules:**
- Exactly one active labor rate and one active machine rate at a time (recommended convention).
- Overhead percent is a system setting, not a rate row (see Settings).

---

## 2.6 Customers

**Purpose:** Lightweight CRM linked to jobs, sales, invoices, quotes.

**Use cases:**
- UC-CUST-1: CRUD a customer (name, email, phone, billing address, shipping address, notes, tags).
- UC-CUST-2: Search by name/email; paginate.
- UC-CUST-3: View a customer's order history, AR balance, lifetime revenue.
- UC-CUST-4: Merge two customer records.

**Business rules:**
- Email is optional but unique when present.
- Merging consolidates jobs, sales, invoices, payments; old record is archived.

---

## 2.7 Products

**Purpose:** SKU catalog of finished goods that can be sold; supports BOM rollup for cost.

**Use cases:**
- UC-PROD-1: CRUD a product (name, auto-generated SKU, optional UPC, description, default sale price, default cost, reorder point, on-hand stock, archived flag, label image).
- UC-PROD-2: Define a bill of materials: rows of (material | supply | sub-product) × quantity × unit.
- UC-PROD-3: Roll BOM up to a computed unit cost.
- UC-PROD-4: Generate printable product labels and barcodes.
- UC-PROD-5: Track per-location stock (Product Studio shows per-location splits).
- UC-PROD-6: Hide archived by default in Product Studio; explicit "Show archived" toggle.

**Business rules:**
- SKU auto-generated; collision logic must handle sequence gaps and material names with spaces (per repo fix history).
- Default product listing endpoint must allow up to 500 rows per page.
- Archived products excluded from default lists and POS scan results.
- A product may be a "kit" (BOM contains sub-products).

---

## 2.8 Inventory

**Purpose:** Single ledger of every stock movement, across materials, supplies, and finished products.

**Use cases:**
- UC-INV-1: Record a transaction: type (production, sale, adjustment, return, waste, receipt, transfer), reference (job_id, sale_id, etc.), quantity delta, location.
- UC-INV-2: List transactions filtered by product/material/supply, type, date.
- UC-INV-3: View low-stock alerts.
- UC-INV-4: Manage inventory locations.
- UC-INV-5: Transfer stock between locations.
- UC-INV-6: Record starting balances at system go-live.
- UC-INV-7: Record scrap and waste with cost write-off posting to accounting.

**Business rules:**
- Every movement is immutable; corrections are new transactions.
- Each transaction may post to the accounting ledger (COGS, inventory asset, scrap expense).
- Stock per location must reconcile with the sum of transactions.

---

## 2.9 Jobs (Print Jobs)

**Purpose:** A planned or in-flight print run with full cost breakdown.

**Use cases:**
- UC-JOB-1: CRUD a job (customer optional, product optional, material(s), plates, grams per plate, print hours, labor minutes, watts, packaging cost, shipping cost, margin override, status [draft/queued/printing/done/canceled]).
- UC-JOB-2: Compute cost & price live (`POST /jobs/calculate`) before saving.
- UC-JOB-3: Multi-part / mixed plates: per-plate qty and assigned printer; **pieces = min(parts) across plates** when mixed.
- UC-JOB-4: Discover jobs from external sources (slicer output, OctoPrint, Moonraker history).
- UC-JOB-5: Filter by status, material, customer, date range, search.
- UC-JOB-6: Job → produces finished product → posts production inventory transactions.

**Business rules:** see cost-engine formulas in [01](01_system_overview.md) and [07](07_module_specifications.md).

---

## 2.10 Printers & Monitoring

**Purpose:** Track each physical printer, assign jobs, view real-time state.

**Use cases:**
- UC-PRT-1: CRUD a printer (name, model, watts, Moonraker host, notes, active flag).
- UC-PRT-2: Connect via Moonraker websocket; subscribe to printer status events.
- UC-PRT-3: View live state: idle, printing, paused, error; current job, progress %, ETA.
- UC-PRT-4: Camera assignment: at most one camera per printer; snapshot proxy.
- UC-PRT-5: Print history events log.
- UC-PRT-6: Production orders: queue across printers.

**Business rules:**
- Websocket manager owns the connection lifecycle; **printer_monitoring is imported at startup** and the app fails to boot without the `websockets` lib.
- Disconnects and reconnects must be transparent to the UI.
- A printer is operationally sensitive — manual state edits should require confirmation.

---

## 2.11 Cameras

**Purpose:** View live or recent imagery of the printer floor.

**Use cases:**
- UC-CAM-1: CRUD a camera (name, stream URL, type [Wyze/go2rtc/RTSP], active).
- UC-CAM-2: Assign / unassign a printer (1:1).
- UC-CAM-3: Fetch snapshot via backend proxy (avoids exposing camera creds to browser).

---

## 2.12 Sales

**Purpose:** Multi-channel order ledger with line items, fees, shipping, status flow, refunds.

**Use cases:**
- UC-SALE-1: CRUD a sale (channel, customer, line items [product/job, qty, unit price], shipping cost, tax, fees, payment method, status [draft/confirmed/shipped/delivered/refunded/canceled], notes).
- UC-SALE-2: Auto-generate sale_number `S-YYYY-NNNN`, race-safe (uses reference-number allocator).
- UC-SALE-3: Compute gross sales, item COGS, gross profit, platform fees, shipping cost, contribution margin.
- UC-SALE-4: Refund a sale (full or partial) — posts reversing inventory + accounting entries; subject to approval thresholds.
- UC-SALE-5: Generate and print shipping label; mark label printed.
- UC-SALE-6: View sales metrics; filter by status, channel, payment method, customer, date.
- UC-SALE-7: POS checkout flow with barcode scan resolution.

**Business rules:**
- Reference number allocator must be race-safe across concurrent sales (was a known fragility; now fixed in source).
- Refunds may require approval if amount > threshold (configurable).
- A confirmed sale posts COGS at FIFO unit cost.
- Sales feed the AR ledger if payment terms = invoice.

---

## 2.13 POS (Point of Sale)

**Purpose:** Fast in-person checkout with barcode scanning.

**Use cases:**
- UC-POS-1: Scan a product barcode → resolves to product → adds line.
- UC-POS-2: Adjust quantity; remove line; apply discount.
- UC-POS-3: Take payment (cash/card/other); complete sale.
- UC-POS-4: Print receipt and/or shipping label.

---

## 2.14 Sales Channels

**Purpose:** Per-channel fee model so sale math is accurate.

**Use cases:**
- UC-CHAN-1: CRUD a sales channel (name, platform fee %, fixed fee per order, active flag).
- UC-CHAN-2: Channel fees applied at sale time and at settlement reconciliation.

---

## 2.15 Marketplace Settlements

**Purpose:** Reconcile Etsy/Amazon payout statements to sales recorded in-app.

**Use cases:**
- UC-SET-1: Import a settlement statement file.
- UC-SET-2: Match settlement lines to sales (auto + manual).
- UC-SET-3: Post settlement journal entry: gross sales, fees, refunds, payout amount.

---

## 2.16 Quotes

**Purpose:** Pre-sale price documents that may convert to invoice/sale.

**Use cases:**
- UC-QUOTE-1: CRUD a quote (customer, lines, validity, status [draft/sent/accepted/declined/expired]).
- UC-QUOTE-2: Auto-generate quote number via reference allocator.
- UC-QUOTE-3: Email a quote (with attachments).
- UC-QUOTE-4: Convert accepted quote → invoice or sale.

---

## 2.17 Invoices & AR

**Purpose:** Customer-facing billing with payment tracking and aging.

**Use cases:**
- UC-INV-1: CRUD an invoice (customer, lines, tax, due date, status [draft/issued/partial/paid/overdue/voided]).
- UC-INV-2: Auto-generate invoice number via reference allocator.
- UC-INV-3: Record payment(s) against an invoice; partial payments allowed.
- UC-INV-4: Apply customer credits (credit notes, prepayments).
- UC-INV-5: Late-fee assessment based on terms.
- UC-INV-6: AR aging report (current, 1-30, 31-60, 61-90, 90+).
- UC-INV-7: Email invoice with PDF.
- UC-INV-8: Recurring invoices on a schedule.

---

## 2.18 Bills, Vendors & Expenses

**Purpose:** AP side — record vendor bills, expense claims, recurring expenses.

**Use cases:**
- UC-BILL-1: CRUD a vendor.
- UC-BILL-2: CRUD a bill (vendor, lines, due date, status, attachments).
- UC-BILL-3: Record bill payment(s).
- UC-BILL-4: Expense categories (chart-of-accounts mapped).
- UC-BILL-5: Employee expense claims; approval workflow.
- UC-BILL-6: Recurring expenses (rent, subscriptions).
- UC-BILL-7: Billable expenses (re-charged to customer on next invoice).

---

## 2.19 Banking & Reconciliation

**Use cases:**
- UC-BANK-1: Import bank statement (CSV/OFX).
- UC-BANK-2: Auto-match transactions via rules; manual match remainder.
- UC-BANK-3: Reconcile a period; lock once balanced.
- UC-BANK-4: Inter-account transfers (between bank/cash accounts).
- UC-BANK-5: Statement match rules CRUD (regex/contains, auto-categorize).
- UC-BANK-6: Bank import mapping (column → field).

---

## 2.20 Accounting Core

**Use cases:**
- UC-ACC-1: Chart of accounts: starter chart on first run; CRUD accounts (asset/liability/equity/revenue/expense, sub-type).
- UC-ACC-2: Journal entries (manual + auto-posted from sales/inventory/payments).
- UC-ACC-3: Accounting periods: open, close, lock.
- UC-ACC-4: Divisions / projects: tag transactions for segment reporting.
- UC-ACC-5: Recurring journal entries.
- UC-ACC-6: Audit log of every accounting mutation.
- UC-ACC-7: Approval workflow for refunds/adjustments above threshold.

---

## 2.21 Tax

**Use cases:**
- UC-TAX-1: Tax profiles (jurisdiction, rate, compound/reverse charge support).
- UC-TAX-2: Sales tax liability report.
- UC-TAX-3: Withholding profiles (1099-style).
- UC-TAX-4: Tax remittance recording.

---

## 2.22 Fixed & Intangible Assets

**Use cases:**
- UC-ASSET-1: CRUD a fixed asset (printer, equipment) with cost, life, salvage, depreciation method.
- UC-ASSET-2: Compute periodic depreciation; post journal entries.
- UC-ASSET-3: CRUD intangible assets (amortization analogue).

---

## 2.23 Reports

**Use cases:**
- UC-RPT-1: Inventory report (on-hand × cost, with CSV).
- UC-RPT-2: Sales report by period (daily/weekly/monthly/yearly), filterable by channel/payment method.
- UC-RPT-3: P&L report (period, with CSV).
- UC-RPT-4: Balance Sheet.
- UC-RPT-5: Cash Flow statement.
- UC-RPT-6: Trial Balance.
- UC-RPT-7: AR aging.
- UC-RPT-8: AP aging.
- UC-RPT-9: Sales tax liability.
- UC-RPT-10: Finance dashboard widgets (KPI tiles).
- UC-RPT-11: Specialized finance reports (cohort, margin trend).
- UC-RPT-12: AI insights summaries (`POST /insights/summary`).

---

## 2.24 Dashboard

**Use cases:**
- UC-DASH-1: Summary tiles (revenue, profit, units sold, low-stock count, queue depth).
- UC-DASH-2: Charts: revenue, materials usage, profit margins, period selectable.

---

## 2.25 Calculator (Standalone)

**Use cases:**
- UC-CALC-1: Ad-hoc cost calculator independent of jobs (one-off pricing).

---

## 2.26 Notes, Attachments, Custom Fields, Form Templates

**Use cases:**
- UC-NOTE-1: Attach freeform notes to most entities.
- UC-ATT-1: Attach files (images, PDFs) to most entities.
- UC-CF-1: Define custom fields on entities (extensible metadata).
- UC-FT-1: Form templates (reusable form configurations).

---

## 2.27 Batch Operations

**Use cases:**
- UC-BAT-1: Bulk edit/archive/delete across products, materials, etc., with preview and confirmation.

---

## 2.28 Approvals

**Use cases:**
- UC-APR-1: An action above threshold creates an approval request; another user approves/rejects; on approval the action proceeds.

---

## 2.29 Email Delivery

**Use cases:**
- UC-EMAIL-1: Send quote/invoice/statement via email with PDF attachment; record delivery state.

---

## 2.30 Shipping & Product Labels

**Use cases:**
- UC-SHIP-1: **Buy** a shipping label via carrier aggregator (EasyPost or ShipStation): inputs are sale ship-to, parcel dims/weight, service level. Output is a label PDF/PNG + tracking number + carrier metadata. The purchase is recorded as a `ShippingLabelPurchased` event and posts a shipping-expense JE.
- UC-SHIP-2: Mark label as printed.
- UC-SHIP-3: Void / refund a label before use (carrier supports this).
- UC-SHIP-4: Receive carrier tracking updates via inbound webhook; update sale tracking status.
- UC-SHIP-5: Static-label fallback for offline use (current v1 behavior preserved).
- UC-LBL-1: Generate product barcode/SKU label sheets, multiple sizes.

**Business rules:**
- A `shipping_carrier` setting selects exactly one aggregator at a time.
- Carrier credentials are server-side only; never exposed to the browser.
- Label purchase cost is captured at purchase time and tied to the sale for COGS / contribution-margin math.

---

## 2.31 Control Center (Admin)

**Use cases:**
- UC-CTRL-1: Aggregated admin view: open approvals, low stock, overdue invoices, failed jobs, websocket health.

---

## 2.32 Webhooks (new in v2)

**Outbound use cases:**
- UC-WH-1: Subscribe a URL to a set of event types; receive HMAC-signed POSTs.
- UC-WH-2: View delivery history and retry failed deliveries.

**Inbound use cases:**
- UC-WH-3: Receive carrier tracking updates and apply to the matching sale.
- UC-WH-4: Receive marketplace order/refund events and create/update sales accordingly.

See [06 §6.6](06_api_catalog.md#66-webhooks--callbacks-v2) for the endpoint surface and event types.

## 2.33 Cross-Cutting

- All list endpoints support pagination, search, and filters.
- All mutations are audit-logged.
- All numeric monetary fields are USD; rounded to 2 decimals on display; computed at full precision.
