# 1. System Overview

## Purpose

A full-stack business operations platform for a small-to-medium 3D-printing business. It replaces a sprawling spreadsheet workflow with a single application that tracks materials, jobs, products, sales, printers, customers, inventory, accounting, and analytics in one consistent ledger.

## Business Context

The owner runs a 3D printing operation that sells finished goods through multiple channels (Etsy, Amazon, direct, in-person POS). Pricing, profitability, and cash flow are sensitive to filament cost, print time, electricity, labor, machine wear, packaging, channel fees, and shipping. Manual spreadsheet workflows for cost calculation, inventory, and accounting are error-prone and don't scale to multi-channel sales, real-time printer monitoring, or proper accounting controls.

## Value Proposition

- **One source of truth** for jobs, products, inventory, sales, accounting.
- **Server-side cost engine** that replicates and standardizes spreadsheet pricing math.
- **Operational visibility** into printers, queue, low stock, and channel performance.
- **Real accounting**: chart of accounts, journal entries, AR/AP, statements, fixed assets, tax.
- **Faster floor work**: POS with barcode scanning, shipping labels, product labels, batch ops.

## High-Level Goals

1. Calculate the true unit cost and selling price of every printed item server-side using transparent, configurable formulas.
2. Track every material, supply, and finished-good movement in a single inventory ledger.
3. Record every sale across every channel, computing platform fees, COGS, and contribution margin automatically.
4. Provide accounting outputs (P&L, Balance Sheet, Cash Flow, Trial Balance, AR aging, Sales Tax Liability) without a separate bookkeeping tool.
5. Monitor printer state in near-real-time (Moonraker websocket integration) and queue jobs against printers.
6. Deliver a fast, dense, operator-grade UI that supports both desktop bookkeeping and physical floor work.

## Success Metrics (proposed for v2)

| Metric | Target |
|---|---|
| Time to record a sale (POS) | < 10 s including barcode scan |
| Cost-calc round-trip | < 200 ms |
| Backend p95 latency, listing endpoints | < 400 ms at 10k rows |
| Time to produce monthly P&L | < 5 s |
| Printer status freshness | < 5 s lag from Moonraker |
| Job-creation-to-first-print | unchanged or faster vs. current |

## Stakeholders / Users

| Role | Needs |
|---|---|
| **Owner / operator** | Pricing, profitability, inventory, accounting — full access |
| **Production staff** | Job queue, plate assignment, printer monitor, mark started/done |
| **Sales / shipping** | POS, sale entry, shipping labels, refunds, settlement reconciliation |
| **Bookkeeper / accountant** | Chart of accounts, journals, reports, period close, tax filings |
| **Future: customer (read-only)** | Order status, invoice view — not in current scope |

The current system has admin-level user accounts only; role separation is informal. A v2 should make roles explicit.

## Current Pain Points (motivation to rewrite)

- **Organic schema growth.** ~65 SQLAlchemy models, ~60 endpoint modules, ~45 service modules. Boundaries between accounting, sales, and inventory blur. Some flows duplicate ledger logic.
- **Test coverage uneven.** Sales/accounting flows have tests; printer monitoring and some accounting subsystems do not.
- **Frontend page-per-feature**. Some flows span many pages (e.g. invoices, recurring, settlements). Information architecture is feature-shaped, not task-shaped.
- **Single-tenant assumption** baked in everywhere; no organization/workspace abstraction.
- **Auth is JWT + bcrypt only**, no MFA, no SSO, no role granularity beyond admin/non-admin flag.
- **Currency is USD-only by design** (per project history); explicitly out of scope.
- **Operationally sensitive subsystems** (inventory ledger, sale-number allocation, printer websockets) carry historical fragility.
- **Docs are extensive but feature-shaped**, scattered across ~70 markdown files — discoverability is poor.

## Scope of Rewrite (recommendation)

- **In scope:** every functional area listed in [02](02_functional_requirements.md).
- **Out of scope for v1 of rewrite:** multi-currency, multi-tenant SaaS, public customer portal, mobile-native apps.
- **Worth reconsidering in v2:** explicit role/permission model, organization/workspace boundary (even single-tenant), event-sourced accounting ledger, typed pricing-engine DSL or rules table instead of hardcoded formula.

## Non-Goals

- Replacing the Moonraker/Klipper firmware integration with a new protocol.
- Building a slicer or G-code processor (the system consumes outputs of slicers, not generates them).
- Replacing payment processors (only records sale metadata; no card processing today).
