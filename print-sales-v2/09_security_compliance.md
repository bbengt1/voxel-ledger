# 9. Security & Compliance

## 9.1 Threat Model (STRIDE-style)

| Threat | Asset | Mitigation today | v2 recommendation |
|---|---|---|---|
| **Spoofing** identity | API access | Bcrypt + JWT bearer | Add MFA; rotate JWT secret on schedule; consider OIDC/SSO |
| **Tampering** with ledger | Inventory, accounting | Service-layer posting, audit log, periods can be closed/locked | Append-only journal table with hash chain |
| **Repudiation** of action | Refunds, period close | Audit log of mutations | Per-user signing keys; immutable audit |
| **Information disclosure** | Customer PII, financials | Auth required on all endpoints; HTTPS via nginx | Field-level encryption for emails/addresses; CSP headers |
| **Denial of service** | API | Rate limiter (120/min/IP), burst configurable | Add per-user limits; circuit-break on slow endpoints |
| **Elevation of privilege** | Admin actions | `is_admin` boolean check | Role/permission model with deny-by-default |

## 9.2 Authentication (v2)

- Email + password.
- Passwords hashed with bcrypt (cost factor in settings).
- **Access tokens** (~15 min expiry) + **refresh tokens** (~30 days, rotating, revocable on password change). Refresh tokens persisted server-side with `jti` + `user_id` + `revoked_at`.
- **No MFA, no SSO** in v2 (single-operator deployment).
- Token rotation: each refresh issues a new refresh token and revokes the prior one (single-use). Reuse of a revoked refresh token revokes the whole family and forces re-login.
- Sessions cleared on 401; frontend redirects to `/login` preserving original URL.
- Password change requires current password and revokes all outstanding refresh tokens.

## 9.3 Authorization — RBAC

v2 uses **RBAC** with a small fixed set of roles. Each user has one or more roles. Permissions are deny-by-default.

| Role | Permissions |
|---|---|
| `owner` | Everything. Only role that can manage users, roles, settings, and close periods. |
| `bookkeeper` | Read/write all accounting (COA, JEs, AR, AP, banking, reconciliations, statements, tax, fixed assets); can close periods only via approval by owner. |
| `production` | Read/write jobs, plates, printers, cameras, production orders, inventory transactions of kind `production` / `waste`. Read-only on sales and accounting. |
| `sales` | Read/write sales, POS, quotes, invoices, customers, shipping labels, refunds (subject to approval threshold). Read-only on accounting. |
| `viewer` | Read-only across the app. |

**Implementation notes:**
- Permissions stored as a flat permission-string set per role (e.g. `sale.create`, `sale.refund`, `period.close`, `user.manage`).
- Route handlers declare required permission(s); a single `requires("perm")` dependency enforces.
- The role-to-permission map lives in code (versioned), not in the DB, so deploys can evolve it safely.
- Approval thresholds (refunds, period close) are checked in addition to role; role gates *eligibility to act*, threshold gates *whether approval is needed*.

## 9.4 Audit Logging

Every mutation in accounting, refunds, period close, approvals, user admin, settings writes an `audit_log` row with:
- `user_id`, `entity_type`, `entity_id`, `action` (create/update/delete/post/refund/approve), `before` (JSON), `after` (JSON), `created_at`, `ip` (recommended for v2).

Audit log is read-only; never bulk-deleted; never truncated by application code.

## 9.5 Data Classification

| Class | Examples | Handling |
|---|---|---|
| **PII** | customer name, email, phone, addresses | Auth-gated; deletable on request (with FK anonymization) |
| **Financial** | invoices, payments, JEs, statements | Auth-gated; period-locked once closed |
| **Operational** | jobs, inventory, printers | Auth-gated; audit-logged when material |
| **Secrets** | DB password, JWT secret, SMTP creds, ADMIN_PASSWORD | Server env file only; never in repo; placeholder values block startup |
| **Camera streams** | RTSP credentials | Never exposed to browser; backend snapshot proxy |

## 9.6 Secrets Management

- Server env file at `/srv/3d-print-sales/env/web01.env`.
- Bootstrap script generates concrete values; placeholder values cause backend startup to refuse.
- Recommendation for v2: keep file-on-host, but add a vault adapter (1Password CLI / SOPS / Bitwarden) for the bootstrap.

## 9.7 Transport Security

- TLS terminated at nginx in production.
- HSTS recommended.
- CORS allow-list driven by settings; default is dev-only origins.
- Same-site / secure cookies if cookies are ever introduced (currently bearer-only).

## 9.8 Input Validation

- All request shapes validated by Pydantic on the backend.
- All client forms validated by zod + react-hook-form.
- File uploads constrained by mime allow-list and size cap.

## 9.9 Output Encoding

- React escapes by default; never `dangerouslySetInnerHTML` for user content.
- CSV exports escape commas/quotes/newlines.

## 9.10 Dependency Hygiene

- Backend requirements pinned exactly in `requirements.txt`.
- Frontend deps pinned in `package.json` with `npm` lockfile.
- Recommend monthly `pip-audit` and `npm audit` runs; integrate into CI for v2.

## 9.11 Compliance Considerations

| Regime | Applicability today | Notes |
|---|---|---|
| **PCI-DSS** | Out of scope | No card data handled — payment method is recorded but no card processing |
| **GDPR** | Marginal | Small US business, but EU customers possible via Etsy/Amazon. Support data export + deletion. |
| **CCPA** | Marginal | Same. |
| **SOC 2** | Not pursued | If pursued in v2: audit log + access reviews + change mgmt + backup tests are foundations |
| **Sales tax** | Yes | Per-jurisdiction tax profiles already implemented; reporting via Sales Tax Liability report |
| **Income tax (US)** | Yes | P&L, BS, depreciation outputs feed CPA |
| **1099 / withholding** | Yes | Withholding profiles implemented |

## 9.12 Backup & Recovery

- Daily PostgreSQL dump.
- Attachments backed up nightly from `/srv/3d-print-sales/data/attachments`.
- Recovery tested at least annually (process to be documented in v2).
- PITR via WAL archiving recommended in v2.

## 9.13 Approval Matrix (recommended)

| Action | Threshold | Approver |
|---|---|---|
| Refund | > $X (configurable) | Admin / refund_approver |
| Period close | always | Admin / controller |
| Adjustment JE inside closed period | always | Admin / controller |
| User create / role change | always | Admin / user_admin |
| Settings change touching cost engine or fees | always | Admin / settings_admin |
| Bulk delete | > N records | Admin |

## 9.14 Known Risks Carried Forward

- Camera credentials embedded in `camera.stream_url` config; recommend separate secret field in v2.
- JWT secret rotation has no operational story; v2 should make rotation safe (key id, multi-key validation window).
- No anomaly detection on logins.
