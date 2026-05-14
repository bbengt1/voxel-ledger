# 10. Testing Documentation

## 10.1 Current Test Surface

| Layer | Framework | Location | Status |
|---|---|---|---|
| Backend unit + integration | `pytest`, `pytest-asyncio` | `backend/tests/` | Established; `conftest.py` sets `TESTING=true` and swaps DB to SQLite via `aiosqlite` |
| Backend HTTP | `httpx` test client | `backend/tests/` | Used for endpoint contract tests |
| Frontend unit/component | `vitest`, `@testing-library/react` | `frontend/src/**/*.test.tsx` | Exists for select pages (e.g. `InsightsPage.test.tsx`, `POSPage.test.tsx`) |
| Frontend build (typecheck) | `tsc -b` via `npm run build` | n/a | Acts as a typecheck gate |
| E2E | none | — | Recommended for v2: Playwright |

**Commands (current):**
```bash
python3 -m pytest backend/tests -q          # backend
cd frontend && npm run build                # typecheck + bundle
cd frontend && npm test                     # vitest
```

## 10.2 Coverage Goals (v2)

| Layer | Target |
|---|---|
| Service layer (business logic) | 80% line + branch |
| API endpoints | 100% on happy path, 80% on error paths |
| Frontend pure utilities | 80% |
| Frontend components | smoke + critical interactions |
| E2E | the 6 user journeys in [08 §8.3](08_ui_ux.md) |

## 10.3 Key Test Scenarios (acceptance)

### Cost Engine
- T-COST-1: Single-plate single-part: pieces = qty.
- T-COST-2: Multi-plate single-part: pieces = sum(qty).
- T-COST-3: Mixed plates: pieces = min(parts per set).
- T-COST-4: Margin override beats setting.
- T-COST-5: Zero hours / zero grams still produces a valid (non-NaN) breakdown.

### Reference Number Allocator
- T-REF-1: 100 concurrent sales produce 100 unique sale numbers in order.
- T-REF-2: Sequence resets at year boundary per prefix.
- T-REF-3: Invoice and sale sequences are independent.

### Sales / Inventory / Accounting
- T-SALE-1: Confirm sale → inventory decremented, COGS posted at FIFO unit cost, revenue JE posted.
- T-SALE-2: Refund full → reversing inventory + reversing JE; sale status updated.
- T-SALE-3: Refund partial → only affected qty/lines reversed.
- T-SALE-4: Refund above threshold creates approval; not posted until approved.
- T-SALE-5: Channel fee % + fixed fee both applied to total.
- T-SALE-6: Contribution margin = gross profit − platform_fee − shipping_cost.

### Material Receipt Valuation
- T-MAT-1: Weighted average cost updates correctly across multiple receipts.
- T-MAT-2: Receipt of zero qty is rejected.
- T-MAT-3: Receipt posts inventory asset JE.

### Product BOM
- T-BOM-1: Rollup with materials only.
- T-BOM-2: Rollup with supplies + sub-products.
- T-BOM-3: Cycle detection: A → B → A is rejected.

### Reports
- T-RPT-1: P&L for a closed period matches sum of JEs.
- T-RPT-2: Trial Balance debit total = credit total.
- T-RPT-3: AR aging buckets match invoice due_at.
- T-RPT-4: Sales tax liability = sum of tax payable posted in period.
- T-RPT-5: Inventory report value = sum(qty × unit_cost) over active products.

### Auth
- T-AUTH-1: Login with valid creds returns JWT; with invalid returns 401.
- T-AUTH-2: Missing bearer → 401.
- T-AUTH-3: Non-admin hitting admin endpoint → 403.
- T-AUTH-4: Password change rejects wrong current password.

### POS
- T-POS-1: Scan UPC resolves to active product.
- T-POS-2: Scan archived product is rejected.
- T-POS-3: Checkout creates a confirmed sale with COGS posted.

### Printer Monitoring
- T-PRT-1: WS disconnect triggers reconnect with backoff.
- T-PRT-2: Adding a new printer opens its WS without restart.
- T-PRT-3: Live state surfaces in API within 5 s of event.

### Settlements
- T-SET-1: Auto-match by external order id.
- T-SET-2: Manual-match remaining lines.
- T-SET-3: Post payout JE balances debit = credit.

### Bank Reconciliation
- T-BNK-1: Imported statement lines visible.
- T-BNK-2: Auto-clear via match rule.
- T-BNK-3: Period cannot be locked while diff ≠ 0.

### Approvals
- T-APR-1: Action above threshold creates pending request.
- T-APR-2: Approval applies the action atomically.
- T-APR-3: Rejection discards.

## 10.4 Performance / Load Baselines

Recommend baselining at v2 cutover:

| Workload | Baseline (current, est.) | Target (v2) |
|---|---|---|
| `GET /products?limit=500` | < 800 ms cold | < 400 ms |
| `GET /sales?date_from=…` 1 year | < 2 s | < 800 ms |
| `POST /jobs/calculate` | < 150 ms | < 100 ms |
| `GET /reports/pl?period=month` | < 3 s | < 1 s |
| POS checkout end-to-end | < 1 s | < 500 ms |
| Concurrent sales (100 over 30 s) | no reference collisions | same |

## 10.5 Integration Test Matrix

| Integration | Required test |
|---|---|
| Moonraker WS | mock server lifecycle (connect, event, disconnect, reconnect) |
| SMTP | green-path send + retry; failure surfaced in delivery log |
| Statement import | each supported format → parsed line count + amounts |
| Camera proxy | success + 4xx/5xx upstream handled |

## 10.6 Migration Tests (v1 → v2)

When v2 is built, write a one-shot data-migration test suite:
- Row counts per table match (or are explained).
- Sum of inventory_transactions per product/material/supply equals on_hand.
- Sum of journal_lines per account equals starting balance + period activity.
- All sale_number / invoice_number / quote_number values preserved.
- Sample of computed sale totals matches v1 export.

## 10.7 Test Data

- Fixtures seeded via `backend/app/seed.py`; v2 should keep a deterministic seed for tests.
- Avoid relying on the production `seed.py` for tests; supply minimal scenario factories instead.

## 10.8 CI Gates (recommended for v2)

- `pytest` must pass.
- `tsc -b` must pass.
- `npm run lint` must pass.
- `npm test` (vitest) must pass.
- New migrations run cleanly on a fresh DB AND on a copy of production schema.
- API contract test: regenerated OpenAPI matches checked-in snapshot.
