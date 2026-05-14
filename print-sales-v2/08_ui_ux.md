# 8. UI / UX Documentation

## 8.1 Screen Inventory

| Page | Route | Purpose |
|---|---|---|
| Login | `/login` | Email/password auth; preserves intended URL |
| Dashboard | `/` | KPI tiles + charts (revenue, materials, profit margin) |
| Control Center | `/control-center` | Admin overview: approvals, low stock, overdue, printer health |
| Calculator | `/calculator` | Standalone cost calculator (no save) |
| Insights | `/insights` | AI summaries, trends |
| **Catalog** | | |
| Products | `/products` | Product list (Product Studio); archived hidden by default |
| Product Editor | `/products/{id}/edit` | BOM, pricing, locations, label image |
| Product Detail | `/products/{id}` | Read view + transactions |
| Product Labels | `/products/labels` | Label sheet generator |
| Materials | `/materials` | Filament inventory CRUD |
| Supplies | `/supplies` | Non-filament inventory |
| Rates | `/rates` | Labor/machine/overhead |
| **Production** | | |
| Jobs | `/jobs` | List + filters |
| Job Form | `/jobs/new`, `/jobs/{id}/edit` | Create/edit with live cost calc |
| Job Detail | `/jobs/{id}` | Cost breakdown + actions |
| Printers | `/printers` | List + state badges |
| Printer Form | `/printers/new`, `/printers/{id}/edit` | |
| Printer Detail | `/printers/{id}` | Live state, history |
| Printer Monitor | `/printers/monitor` | Wall view across all printers |
| **Sales** | | |
| Sales | `/sales` | List + filters + metrics |
| Sale Form | `/sales/new`, `/sales/{id}/edit` | |
| Sale Detail | `/sales/{id}` | Lines, fees, refund, label |
| POS | `/pos` | Barcode scan + checkout |
| Sales Channels | `/sales/channels` | Per-platform fees |
| Customers | `/customers` | CRM |
| Orders | `/orders` | Pre-sale orders |
| **Accounting** | `/accounting/*` | Chart of accounts, journals, periods, divisions, fixed assets, intangibles, tax, withholding, approvals, audit log, recurring JEs, banking, reconciliations, statement imports, match rules, expense claims, bills, vendors, settlements, AR, invoices, recurring invoices, credit/debit notes |
| **Reports** | `/reports/*` | Inventory, Sales, P&L, BS, CF, TB, AR/AP aging, sales tax |
| **Admin** | `/admin/*` | Users, settings |

## 8.2 Navigation

- Persistent left sidebar grouped by bounded context (Catalog, Production, Sales, Accounting, Reports, Admin).
- Top bar: global search (recommended for v2; partial today), theme toggle, profile menu.
- Breadcrumbs on detail pages.
- Active section highlighted.

## 8.3 User Journeys

### J1 — Quote a custom print
```
Dashboard → Jobs → New → fill material/grams/hours/labor → /jobs/calculate
  → save Draft → (optional) Customer link → Quote → email
```

### J2 — Confirm a marketplace order
```
Dashboard → Sales → New (Etsy channel) → add product line → confirm
  → inventory decremented, COGS posted, JE booked, sale_number assigned
```

### J3 — In-person POS sale
```
POS → scan barcode → review cart → take payment → checkout → print receipt
```

### J4 — Monthly close
```
Reports → P&L → review → fix outliers in Accounting → Period → close month
  → re-export P&L → Bank → Reconcile → lock period
```

### J5 — Reconcile Etsy payout
```
Settlements → Import statement → auto-match → manual-match leftovers
  → post settlement → Bank → see payout deposit reconciled
```

### J6 — Refund
```
Sale Detail → Refund → enter amount → if > threshold submit for approval
  → admin approves → inventory restored, JEs reversed, status updated
```

### J7 — Receive filament
```
Materials → material row → Receipt → qty grams + unit cost
  → on_hand_g increases, cost_per_g recomputed weighted avg, JE posted
```

## 8.4 Wireframe Notes (text descriptions)

Detailed wireframes were not produced for this reverse-engineering pass. Key layout conventions to preserve in v2:

- **List pages**: search left, filters chip-row above table, primary action (New) top-right; dense table; bulk-select column.
- **Form pages**: two-column on desktop (form + live preview when applicable, e.g. Job cost panel); single-column on mobile.
- **Detail pages**: header strip with title + status + primary actions; tabbed body (Overview, Items, History, Attachments, Notes).
- **POS**: cart on right (~40%), scan + product browser on left; large primary CTAs (Fitts).
- **Printer Monitor**: grid of cards, one per printer; live image + status pill + progress bar.

## 8.5 Form Field Specifications

| Field type | Validation |
|---|---|
| Email | RFC 5322 simplified, optional unless required |
| Money | decimal, ≥ 0, 2 places |
| Quantity (grams/units) | decimal, ≥ 0, configurable precision |
| Percentage | 0–100, decimal |
| Date | ISO 8601 date or datetime |
| SKU | auto-generated; user-editable but must remain unique |
| UPC | optional; 8/12/13 digit; unique when set |
| Status enums | constrained dropdowns; transitions enforced server-side |

All fields use zod schemas on the client and Pydantic on the server. v2 should generate one from the other.

## 8.6 Accessibility Notes

- Target WCAG 2.1 AA.
- All inputs labeled; error messages associated via `aria-describedby`.
- Keyboard reachable for all primary actions; visible focus rings.
- Color is never the only signal (status pills include text label and icon).
- POS and Job Form must be operable with keyboard alone.
- Dark/light themes both meet contrast targets.

## 8.7 UX Laws Applied (project ruleset)

Already documented in `agents.md`:

- **Aesthetic-Usability:** polish, but don't hide weak IA.
- **Doherty (400 ms):** ack quickly; optimistic UI for slow ops.
- **Fitts:** primary/frequent actions large and close.
- **Hick:** progressive disclosure; sensible defaults.
- **Jakob:** familiar patterns by default.
- **Common Region / Proximity / Similarity / Uniform Connectedness:** grouping by spacing/containers; not by color alone.
- **Prägnanz:** simplify until structure is obvious.
- **Miller:** chunk info; don't treat 7±2 as a hard limit.
- **Occam:** simplest interaction that solves the real problem.
- **Pareto:** optimize the 20% most-used flows.

## 8.8 Notifications & Feedback

- Toast notifications (sonner) for transient success/error.
- Inline form errors for validation.
- Empty states with a primary CTA on every list.
- Skeleton loaders on initial load; inline spinners on actions.
- ErrorBoundary at the route shell with a clear recovery path.

## 8.9 Theming

- Light + Dark via Tailwind; persisted to `localStorage`; defaults to system preference.
- Brand tokens centralized in Tailwind config; v2 should keep a design-tokens layer.

## 8.10 Responsive Behavior

- Desktop-first (operator workstation is the primary device).
- Tablet supported for POS and Printer Monitor.
- Mobile is best-effort for monitoring/checking; not a target for data entry.
