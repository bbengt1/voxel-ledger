# Changelog

One entry per shipped phase. Links go to the merge commit's PR. Phase
sub-items are listed where they shipped as separate PRs.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/);
the project does not tag releases — `main` is the deployed truth.

## Phase 11 — Notifications & extensions

- [#202](https://github.com/bbengt1/voxel-ledger/pull/202) Phase 11.5: webhooks + control center + batch UI
- [#201](https://github.com/bbengt1/voxel-ledger/pull/201) Phase 11.4: control center endpoint
- [#200](https://github.com/bbengt1/voxel-ledger/pull/200) Phase 11.3: batch operations (preview + commit)
- [#199](https://github.com/bbengt1/voxel-ledger/pull/199) Phase 11.2: inbound webhooks (carrier + marketplace)
- [#198](https://github.com/bbengt1/voxel-ledger/pull/198) Phase 11.1: outbound webhook dispatcher

## Phase 10 — Reporting & dashboards

- [#192](https://github.com/bbengt1/voxel-ledger/pull/192) Phase 10.8b: sales / inventory reports + dashboard home
- [#191](https://github.com/bbengt1/voxel-ledger/pull/191) Phase 10.8a: financial-statement report UI (P&L / BS / CF / TB)
- [#190](https://github.com/bbengt1/voxel-ledger/pull/190) Phase 10.7: AI insights summary worker
- [#189](https://github.com/bbengt1/voxel-ledger/pull/189) Phase 10.6: dashboard KPI tiles endpoint
- [#188](https://github.com/bbengt1/voxel-ledger/pull/188) Phase 10.5: sales-by-period + inventory valuation reports
- [#187](https://github.com/bbengt1/voxel-ledger/pull/187) Phase 10.4: trial balance report
- [#186](https://github.com/bbengt1/voxel-ledger/pull/186) Phase 10.3: cash flow report (indirect method)
- [#185](https://github.com/bbengt1/voxel-ledger/pull/185) Phase 10.2: balance sheet report
- [#184](https://github.com/bbengt1/voxel-ledger/pull/184) Phase 10.1: income statement (P&L) report

## Phase 9 — Specialized accounting

- [#173](https://github.com/bbengt1/voxel-ledger/pull/173) Phase 9.10b: specialized accounting UI — tax + settlements
- [#172](https://github.com/bbengt1/voxel-ledger/pull/172) Phase 9.10a: specialized accounting UI — assets + depreciation + withholding
- [#171](https://github.com/bbengt1/voxel-ledger/pull/171) Phase 9.9: settlement auto-match + payout JE
- [#170](https://github.com/bbengt1/voxel-ledger/pull/170) Phase 9.7: withholding profiles
- [#169](https://github.com/bbengt1/voxel-ledger/pull/169) Phase 9.4: asset disposal
- [#168](https://github.com/bbengt1/voxel-ledger/pull/168) Phase 9.6: tax liability + remittance
- [#167](https://github.com/bbengt1/voxel-ledger/pull/167) Phase 9.3: depreciation run worker
- [#166](https://github.com/bbengt1/voxel-ledger/pull/166) Phase 9.5: tax profiles + compound/reverse-charge
- [#165](https://github.com/bbengt1/voxel-ledger/pull/165) Phase 9.8: marketplace settlement imports
- [#164](https://github.com/bbengt1/voxel-ledger/pull/164) Phase 9.2: depreciation schedule generator
- [#163](https://github.com/bbengt1/voxel-ledger/pull/163) Phase 9.1: fixed + intangible assets foundation

## Phase 8 — AP + Banking

- [#152](https://github.com/bbengt1/voxel-ledger/pull/152) Phase 8.12b: Banking UI (imports, mappings, transactions, match rules, reconciliation, transfers)
- [#151](https://github.com/bbengt1/voxel-ledger/pull/151) Phase 8.12a: AP UI (vendors, bills, bill payments, recurring, expenses)
- [#150](https://github.com/bbengt1/voxel-ledger/pull/150) Phase 8.11: bank reconciliation + inter-account transfers
- (earlier 8.x slices land via the merge history under [`phase-8`](https://github.com/bbengt1/voxel-ledger/labels/phase-8))

## Phase 7 — AR

- See [`phase-7`](https://github.com/bbengt1/voxel-ledger/labels/phase-7) for the per-slice PRs (quotes, invoices, payments, customers, recurring invoices, late fees, statements).

## Phase 6 — Sales pathway

- See [`phase-6`](https://github.com/bbengt1/voxel-ledger/labels/phase-6) (sales channels, sales + items, POS, refunds, shipping).

## Phase 5 — Production

- [#87](https://github.com/bbengt1/voxel-ledger/pull/87) Phase 5.2: jobs + plates (multi-plate, multi-printer, pieces math)
- [#86](https://github.com/bbengt1/voxel-ledger/pull/86) Phase 5.1: printers + cameras (CRUD + backend snapshot proxy)

## Phase 4 — Accounting core

- [#75](https://github.com/bbengt1/voxel-ledger/pull/75) Phase 4.6: accounting UI (CoA tree, journal form, period management, approvals, budgets)
- [#74](https://github.com/bbengt1/voxel-ledger/pull/74) Phase 4.5: divisions + budgets per account
- [#73](https://github.com/bbengt1/voxel-ledger/pull/73) Phase 4.4: approval workflow (generic request/approve/reject + threshold gating)
- [#72](https://github.com/bbengt1/voxel-ledger/pull/72) Phase 4.3: accounting periods (open/close/lock state machine)
- [#71](https://github.com/bbengt1/voxel-ledger/pull/71) Phase 4.2: journal entries (debit/credit, event-sourced, balance projection)
- [#70](https://github.com/bbengt1/voxel-ledger/pull/70) Phase 4.1: chart of accounts (hierarchical, typed)

## Phase 3 — Inventory

- [#61](https://github.com/bbengt1/voxel-ledger/pull/61) Phase 3.4: inventory UI (transactions, alerts, starting balances)
- [#59](https://github.com/bbengt1/voxel-ledger/pull/59) Phase 3.3: on-hand projection & low-stock alerts
- [#56](https://github.com/bbengt1/voxel-ledger/pull/56) Phase 3.2: inventory transactions ledger
- [#54](https://github.com/bbengt1/voxel-ledger/pull/54) Phase 3.1: inventory locations (CRUD)

## Phase 2 — Catalog

- [#48](https://github.com/bbengt1/voxel-ledger/pull/48) Phase 2.6: attachments & notes (polymorphic refs, local-disk storage)
- [#47](https://github.com/bbengt1/voxel-ledger/pull/47) Phase 2.5: custom fields & form templates
- [#46](https://github.com/bbengt1/voxel-ledger/pull/46) Phase 2.4: BOM (polymorphic components, cycle detection, cost rollup)
- [#45](https://github.com/bbengt1/voxel-ledger/pull/45) Phase 2.2: supplies & rates
- [#44](https://github.com/bbengt1/voxel-ledger/pull/44) Phase 2.3: products (auto-SKU, optional UPC)
- [#43](https://github.com/bbengt1/voxel-ledger/pull/43) Phase 2.1: materials & receipts (weighted-average cost-per-gram)

## Phase 1 — Platform plumbing

- [#34](https://github.com/bbengt1/voxel-ledger/pull/34) Phase 1.6: users & roles admin
- [#32](https://github.com/bbengt1/voxel-ledger/pull/32) Phase 1.5: settings service (typed key-value, safe defaults)
- [#33](https://github.com/bbengt1/voxel-ledger/pull/33) Phase 1.4: audit log projection & query API
- [#30](https://github.com/bbengt1/voxel-ledger/pull/30) Phase 1.3: race-safe reference allocator
- [#31](https://github.com/bbengt1/voxel-ledger/pull/31) Phase 1.2: projection engine (handler registry, sync projection, replay)
- [#29](https://github.com/bbengt1/voxel-ledger/pull/29) Phase 1.1: event log core

## Phase 0 — Bootstrap

- [#20](https://github.com/bbengt1/voxel-ledger/pull/20) Phase 0.8: frontend login + protected-route shell + theme toggle
- [#19](https://github.com/bbengt1/voxel-ledger/pull/19) Phase 0.10: local bootstrap & contributor onboarding
- [#18](https://github.com/bbengt1/voxel-ledger/pull/18) Phase 0.6: CI pipeline (lint, type-check, test, codegen drift)
- [#17](https://github.com/bbengt1/voxel-ledger/pull/17) Phase 0.5: OpenAPI → TypeScript codegen pipeline
- [#16](https://github.com/bbengt1/voxel-ledger/pull/16) Phase 0.9: deployment runbook + n8n workflow stub
- [#15](https://github.com/bbengt1/voxel-ledger/pull/15) Phase 0.7: auth scaffolding (JWT + rotating refresh + RBAC)
- [#14](https://github.com/bbengt1/voxel-ledger/pull/14) Phase 0.3: Docker Compose dev + prod stacks
- [#12](https://github.com/bbengt1/voxel-ledger/pull/12) Phase 0.4: React 19 + Vite + Tailwind 4 + Radix skeleton
- [#11](https://github.com/bbengt1/voxel-ledger/pull/11) Phase 0.2: backend skeleton (FastAPI + Postgres + Alembic)
- [#10](https://github.com/bbengt1/voxel-ledger/pull/10) Phase 0.1: monorepo scaffolding
