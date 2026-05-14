# 3. Non-Functional Requirements

## 3.1 Performance

| Concern | Target |
|---|---|
| API p95 latency, simple GETs | < 200 ms |
| API p95 latency, list endpoints (≤500 rows) | < 400 ms |
| Cost-calc endpoint | < 200 ms |
| Report generation (period ≤ 1 year) | < 5 s |
| Printer status freshness | < 5 s lag from Moonraker |
| Frontend first contentful paint | < 1.5 s on broadband |
| Frontend time-to-interactive | < 2.5 s |
| POS scan → line added | < 500 ms |

**Notes from current system:**
- Default `GET /products` limit was raised 100 → 500 after a real pain point; the new system should default to cursor pagination and allow larger pages.
- Moonraker websocket connections are long-lived and reused; the new system should preserve that pattern.

## 3.2 Scalability

The current installation is single-tenant, single-host, low-volume (small business, <100 sales/day, <50 active printers). Architectural targets:

- **Vertical first.** A single 4-core / 8 GB VM should handle 10× current volume.
- **Stateless API.** All session state in JWT or DB; backend nodes are interchangeable.
- **Background work** (settlements imports, recurring invoice generation, depreciation runs, AI insights) should be deferrable to a worker process — currently inlined.
- **Database** is PostgreSQL; queries should be index-covered; no full-table scans on hot paths.

## 3.3 Reliability & Availability

| Concern | Target |
|---|---|
| Uptime | 99.5% (small business; off-hours maintenance acceptable) |
| RPO (data loss tolerance) | ≤ 24 h via nightly backup; ideally point-in-time recovery |
| RTO (recovery time) | ≤ 2 h |
| Migrations | Always run on every schema-changing deploy (current `alembic upgrade head`); v2 should keep this gate enforced |
| Startup hard dependencies | Minimize — current app refuses to start if Moonraker `websockets` lib missing; consider lazy-loading printer subsystem |

**Reliability rules:**
- Every accounting mutation is durable before HTTP 200.
- Reference number allocation is race-safe (sale_number, invoice_number, quote_number).
- Inventory ledger entries are atomic with the business action that created them.
- Background failures (settlement import, email delivery) are retryable and surface in the UI.

## 3.4 Security

See [09_security_compliance.md](09_security_compliance.md) for the full threat model. Key requirements:

- TLS in transit (terminated at nginx/ingress today).
- Bcrypt at rest for passwords; secrets never in repo.
- JWT with short expiry + refresh; revocation on password change.
- Rate limit on the public API (currently 120 req/min/IP, burst configurable).
- CORS allow-list driven from settings.
- Audit log for every accounting mutation, with user, before/after, timestamp.
- Approval workflow for refunds/adjustments above configurable threshold.
- Camera credentials never exposed to browser (snapshot proxy).
- No PII beyond customer name/email/address/phone — no PCI scope (no card processing).
- The seed enforces: tracked placeholder secrets in env block startup.

## 3.5 Maintainability

- Source code organized by **domain bounded contexts**, not by technical layer. The current repo mixes — v2 should pick one and stick to it.
- Per-domain service layer; thin HTTP handlers; no business logic in React components or route handlers.
- API, schema, model, and frontend types kept in lock-step. **v2 generates the frontend TypeScript client from the backend OpenAPI spec** via a prebuild step; CI fails on drift.
- Tests live next to code and cover service-layer business logic. Target coverage: 80% on services, 60% overall.
- Documentation is a product surface; updates required as part of any behavior-changing PR.

## 3.6 Extensibility

- Custom fields on entities (currently shipping).
- Form templates (currently shipping).
- BOM rows accept material | supply | sub-product polymorphism; v2 should formalize this with a typed component reference.
- Sales channel fee model is data-driven (no code change to add a channel).
- Tax profiles support compound and reverse charge.
- New report types should be add-only (no breaking changes to existing reports).

## 3.7 Observability

- Health endpoint `/health`.
- Structured logs (recommend JSON) with request id.
- Per-request timing; per-DB-query timing in dev.
- Printer monitor exposes websocket health.
- Background workers expose last-run + last-success per job.
- Recommend OpenTelemetry traces in v2 (not present today).

## 3.8 Usability

See [08_ui_ux.md](08_ui_ux.md) for the UX-laws ruleset already adopted by the project. Highlights:

- Doherty threshold: ack within 400 ms; optimistic UI for slow ops.
- Fitts: primary actions large and close.
- Hick: progressive disclosure; sensible defaults.
- Jakob: familiar patterns by default.
- Pareto: optimize the 20% most-used workflows.

## 3.9 Accessibility

- WCAG 2.1 AA target.
- Keyboard navigation for all primary flows, especially POS and job creation.
- Color contrast meets AA in both dark and light themes.
- Form errors associated with inputs via `aria-describedby`.

## 3.10 Internationalization / Localization

- USD only — explicitly out of scope (per project memory).
- English-only UI today; v2 should still wrap strings in an i18n helper to allow localization later.
- Dates display in user's local timezone; stored in UTC.

## 3.11 Backup, Archiving, Retention

- Nightly PostgreSQL backup; offsite copy retained 30 days.
- Audit log retained indefinitely.
- Inventory transactions retained indefinitely (ledger).
- Attachments retained indefinitely (object store recommended for v2; currently filesystem).
- Personal data: customer records support deletion (with anonymization of historical references) for compliance.

## 3.12 Technical Constraints

- Must deploy to a single Linux VM via Docker Compose for at least the v2.0 release (parity with current ops).
- Must run alongside the existing PostgreSQL 16 instance during migration.
- Must integrate with Moonraker (Klipper) websockets — non-negotiable for printer monitoring.
- Must produce CSV exports for the reports listed in [02 §2.23](02_functional_requirements.md).
- Must support at-rest filesystem persistence for attachments at the existing mount.
