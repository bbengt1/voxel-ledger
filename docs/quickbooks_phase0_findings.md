# QuickBooks Online integration — Phase 0 findings (hard gate)

Tracks issue **#313** under epic **#312** (replace local accounting/bookkeeping with QBO as system of record).

This document replaces the **refuted/unverified** claims from the original research pass with values
**verified against live Intuit documentation** (`developer.intuit.com`), so Phases 1–5 build on facts.
Each fact lists its source + a confidence level. Items that still require a human action (registering
the sandbox app, running the spike) are tracked in [§9 Remaining human steps](#9-remaining-human-steps).

> **Verification method:** Intuit's doc site is a JS-rendered SPA. Values below were read either from
> Intuit's static machine-readable discovery JSON, or by rendering the live SPA pages in a real browser
> and extracting the verbatim text (token lifetimes, scope, rotation). Where a value could only be
> corroborated via Intuit-controlled channels (official blog, SDK docs) rather than the canonical
> reference page, it is marked **(corroborated)**.

---

## 1. OAuth 2.0 — tokens, endpoints, scope, rotation  ✅ resolves refuted item #1 & #3

| Fact | Value | Source / confidence |
|---|---|---|
| Access-token TTL | **3600 s (60 min)** — `expires_in: 3600` | OAuth 2.0 page, verbatim. **High** |
| Refresh-token TTL | **100 days, rolling** — `x_refresh_token_expires_in: 8640000` | OAuth 2.0 page: "Refresh tokens have a rolling expiry of 100 days." **High** |
| Refresh-token hard cap | **5 years** — `x_refresh_token_hard_expires_in: 157680000` (only returned if `x-include-refresh-token-hard-expires-in: true`) | OAuth 2.0 page, verbatim. **High** |
| **Rotation rule** | On every code-exchange **and** refresh, the response contains a `refresh_token`. **Always persist the latest `refresh_token` from the most recent response.** The 100-day rolling clock resets when a new refresh token is issued. After 100 days idle (or the 5-year hard cap), the user must re-authorize. | OAuth 2.0 page, verbatim: "Always store the latest refresh_token value from the most recent API server response." **High** |
| Authorization endpoint | `https://appcenter.intuit.com/connect/oauth2` (same sandbox + prod) | Discovery JSON. **High** |
| Token endpoint (code-exchange **and** refresh) | `POST https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer` | OAuth 2.0 page + discovery JSON. **High** |
| Revoke endpoint | `POST https://developer.api.intuit.com/v2/oauth2/tokens/revoke` — body `{"token": "<bearer or refresh>"}`; 200 on success. Pass `realmId` as a query param to identify the company on disconnect. | OAuth 2.0 page + discovery JSON. **High** |
| Accounting scope | **`com.intuit.quickbooks.accounting`** (space-delimited if combined with `openid`/`profile`/`email`). UI labels it "QuickBooks Online Accounting scope." | OAuth 2.0 page (friendly name) + discovery JSON (OIDC scopes). **High** on string (industry-canonical), **Med** that the page prints the literal string. |
| Incremental scopes | **Supported & recommended** — "We recommend apps request scopes incrementally… rather than all scopes up front." → the refuted "scope change requires full OAuth re-run" claim is **false**. | OAuth 2.0 page, verbatim. **High** |
| `response_type` | `code` only; `token_endpoint_auth_methods`: `client_secret_post` / `client_secret_basic`; id_token alg `RS256`; issuer `https://oauth.platform.intuit.com/op/v1`. | Discovery JSON. **High** |
| Discovery docs | Prod: `https://developer.api.intuit.com/.well-known/openid_configuration/` · Sandbox: `…/openid_sandbox_configuration/`. Only `userinfo_endpoint` differs between them. | Discovery JSON. **High** |

**Phase-1 implication:** the token-refresh helper must **read the `refresh_token` from every refresh
response and overwrite the stored one atomically** (don't assume it's unchanged). Treat a 400/`invalid_grant`
on refresh as "chain broken → surface reconnect." Store `access_token_expires_at` (now+3600 s) and
`refresh_token_expires_at` (now+100 days) on each write; proactively refresh access tokens before expiry.

---

## 2. Update semantics — sparse vs full + SyncToken  ✅ resolves refuted item #2

- **Sparse update is supported** on the entities we use. Update with `"sparse": true` + `Id` + current `SyncToken`;
  only supplied fields change. A full update (no `sparse`) **clears** omitted fields — so always use sparse for
  partial edits. *(High for Customer/Vendor/Item/Invoice/Payment/Bill/BillPayment; **Med** — "very likely, template-confirmed" — for SalesReceipt/CreditMemo/VendorCredit/Account/JournalEntry; no entity was found to be full-update-only.)*
- **SyncToken** is optimistic-concurrency: read entity → get current `SyncToken` → send it on update → it increments on success.
  A stale token returns **error 5010 "Stale Object Error"**. Recovery: re-read, then retry. *(High)*
- The original "must send the full object; sparse unreliable" claim is **refuted**.

**Implication:** the `qbo_entity_map` / `qbo_sync_outbox` must persist the latest `SyncToken` per entity and
refresh-on-5010-then-retry.

Sources: entity reference pages under `…/docs/api/accounting/all-entities/<entity>`; `…/learn/learn-basic-field-definitions`;
help article "QuickBooks Online API Error Code 5010".

---

## 3. Idempotency — **use `RequestId`**  ✅ resolves open item #4 (idempotency)

- Intuit's **canonical** duplicate-avoidance mechanism is the **`requestid` query parameter** on a create/transaction call.
  "All developers are strongly recommended to send in the RequestID for every API request so that idempotency is
  guaranteed… the service can replay the request… data is not duplicated." A repeat with the same `requestid` returns
  the **same response** instead of creating a duplicate. "If no request-id is specified, a duplicate transaction with a
  new ID is created." Generate a UUID/GUID; **must be unique per company**. *(High — Intuit help "What is RequestId and its usage")*
- Batch items carry a **`bId`** for correlating responses within one batch — **not** a cross-request idempotency key.
- "Query by `DocNumber` before create" is a community pattern, **not** the official mechanism (and DocNumber uniqueness
  is a per-company preference, so unreliable). Do **not** rely on it.

**Decision (locked for Phase 3):** assign a stable **`requestid` (UUIDv4) per `qbo_sync_outbox` row at enqueue time**;
reuse the same `requestid` on every retry of that row. This makes worker retries and 429 replays safe with zero dedupe logic.

---

## 4. JournalEntry mapping (for postings with no native doc)  ✅ resolves new JE task

For depreciation, disposals, tax remittances, transfers, deposit slips, and matcher postings → push a **JournalEntry**:

- `Line[]`, each: `DetailType: "JournalEntryLineDetail"`, `Amount`, and `JournalEntryLineDetail` with
  `PostingType: "Debit"|"Credit"` and `AccountRef`.
- **Must balance**: Σ Debit lines = Σ Credit lines (else rejected). At least one Debit and one Credit line.
- **AR/AP lines need an `Entity`**: a line hitting an Accounts-Receivable account requires `Entity` = a **Customer**;
  an Accounts-Payable line requires `Entity` = a **Vendor**. QBO (unlike Desktop) allows multiple AR/AP lines in one JE.

*(High on structure / Med on the exact "Required" column — page is SPA-rendered; corroborated via Intuit indexed snippets.
The spike (§9) creates one JournalEntry to confirm end-to-end.)*

Source: `…/docs/api/accounting/all-entities/journalentry`.

---

## 5. Rate limits, batch, base URLs, minor version  ✅ resolves refuted "40 concurrent"

| Fact | Value | Confidence |
|---|---|---|
| Per-realm throughput | **500 requests/min/realm** (a batch counts as 1) | High |
| Concurrency | **10 concurrent/realm** (the "40" claim is **refuted**) | High |
| Throttle error | `errorCode=003001` "ThrottleExceeded", **HTTP 429** — back off, retry with **same `requestid`** | High |
| Batch endpoint | `POST /v3/company/{realmId}/batch`, **≤30 ops/request**, run serially (later items can't see earlier results) | High |
| Batch-specific cap | **120 requests/min/realm** for the batch endpoint (sandbox 2025-08-15, **production 2025-10-31**) | High (corroborated, Intuit blog) |
| Minor version | **Pin `minorversion=75`** (latest). Minor versions **1–74 deprecated 2025-08-01**; values <75 are ignored and treated as 75. | High (corroborated, Intuit blog) |
| Base URLs | Prod `https://quickbooks.api.intuit.com` · Sandbox `https://sandbox-quickbooks.api.intuit.com`; path `/v3/company/{realmId}/…` | High |

**Implication:** the Phase-3 client wrapper enforces ≤10 concurrent + token-bucket ~500/min, appends `?minorversion=75`
(and `&requestid=<uuid>` on writes), batches where it helps (≤30, and stay under 120 batch-calls/min).

Sources: help "API call limits and throttling" / "QuickBooks Online API Best Practices"; Intuit blog
"Upcoming changes to the Accounting API" (2025-08-13); "Changes to our Accounting API…" (2025-01-21).

---

## 6. Reports + link-out story  ✅ resolves reporting task — ⚠️ design constraint

- **QBO has a Reports API**: `GET /v3/company/{realmId}/reports/{reportName}` for **BalanceSheet, ProfitAndLoss,
  TrialBalance, GeneralLedger, AgedReceivables(+Detail), AgedPayables(+Detail), CashFlow** — i.e. data-out for every
  report we're removing. Hard limit ~**400,000 cells/response** (date-chunk large queries). *(High — Intuit Run-Reports
  workflow + SDK class list.)*
- **⚠️ No supported UI deep-links.** Intuit does **not** document a stable URL to deep-link a user into a *specific report*
  in the QBO web UI (`*.qbo.intuit.com` URLs are undocumented and change). *(High — absence of evidence.)*

**Decision for Phase 5 "link out":** the admin "Open in QuickBooks" link should target the **QBO web app generically**
(`https://qbo.intuit.com` / `https://app.qbo.intuit.com`), **not** a per-report deep link. If stakeholders later want
financial statements *in-app* without leaving, the supported path is the **Reports API** (note: CorePlus-metered — see §7),
not deep-linking — that would be a follow-up, not part of the chosen link-out plan.

---

## 7. Go-live, app review, and **cost**  ✅ resolves go-live/cost task — ⚠️ new metering

- **Go-live:** to unlock **production** OAuth keys you must enable Production on the app and **complete Intuit's app-assessment
  questionnaire** — required for **every** app, including a **private single-company** integration. **App Store listing/review is
  NOT required** for a private single-company app. Sandbox/dev keys only work on sandbox; prod keys only on live companies (not interchangeable). *(High, corroborated.)*
- **⚠️ Cost — App Partner Program (new, full pricing 2025-11-01):** API calls are split into
  - **Core** (data-**in**: create/update invoices, bills, customers, JEs…) — **unmetered / free**.
  - **CorePlus** (data-**out**: reads, queries, **reports**, **CDC**) — **metered**. Free **Builder** tier = **500,000 CorePlus
    credits/month**; paid tiers above that (Silver $300/mo→1M, Gold $1,700→10M, Platinum $4,500→75M).
  - *(High that the program exists; Med on exact dollar/credit figures — Intuit partner-FAQ is SPA-rendered, figures via Intuit-aligned summaries. Re-confirm live before relying on numbers.)*

**Implication:** our **writes are free**; our **metered usage is only reconciliation + CDC reads** (Phase 4). At one company /
low volume we're far under 500k/month → **effectively free**, but design Phase 4 polling to be economical (CDC over full re-queries)
so we never approach the cap.

---

## 8. Python libraries + runtime  ⚠️ runtime caveat → library decision

| Lib | Version | License | Python support | Note |
|---|---|---|---|---|
| `intuit-oauth` (intuitlib) | **1.2.6** (2024-08-01) | Apache-2.0 | `py3-none-any`; 3.12 in changelog, **no explicit 3.13 classifier** | **Intuit-maintained** (`intuit/oauth-pythonclient`) |
| `python-quickbooks` | **0.9.12** (2025-04-16) | MIT | classifiers **3.5–3.12; no 3.13** | Community (`ej2/python-quickbooks`), active |

Our backend image is **Python 3.13-slim** (`requires-python >=3.12`). Neither lib advertises 3.13.

**Decision (locked):**
- Use **`intuit-oauth`** for the OAuth handshake + refresh (pure-python, Intuit-maintained, low 3.13 risk — confirm in the spike).
- Use **raw `httpx`** (already a dependency) for all v3 REST/batch/CDC calls **instead of `python-quickbooks`**, because (a) it
  avoids the 3.13 classifier risk, and (b) we need explicit control over `minorversion`, `requestid`, batch, and 429 backoff anyway.
  Keep `python-quickbooks` as a **reference implementation only** (don't add it as a dependency unless the spike shows we need it).

---

## 9. Remaining human steps (need an Intuit account — not automatable)

These are the parts of #313 a person with the Intuit login must do; everything else above is done.

- [ ] **Register an Intuit developer app (sandbox)** at `developer.intuit.com`: create app, select **QuickBooks Online Accounting**
      scope, set redirect URI (dev), note **sandbox `client_id` / `client_secret`** and the **sandbox company `realmId`**.
- [ ] Put sandbox creds in **`/srv/voxel-ledger/env/web02.env`** (and a local `.env`) following the existing secret pattern —
      never commit. (Prod keys later require the app-assessment questionnaire, §7.)
- [ ] **Run the spike** ([`docs/spikes/quickbooks_spike.py`](spikes/quickbooks_spike.py)) against the sandbox: complete the
      auth-code flow, capture `realmId`, read `CompanyInfo`, create+read one `Customer`, create one `JournalEntry`.
      Confirm `intuit-oauth` imports/works on **Python 3.13**. Spike output is disposable — record pass/fail here, don't merge app code.
- [ ] Record the spike result + re-confirm the §7 cost figures against the live partner-FAQ, then check the boxes on #313.

---

## 10. Decisions locked by Phase 0 (carry into later phases)

1. **Tokens:** access 1 h / refresh 100-day rolling / 5-yr hard cap; **persist the rotated `refresh_token` from every response**;
   `invalid_grant` ⇒ reconnect. (Phase 1)
2. **Idempotency:** one **`requestid` UUID per outbox row**, reused on retry. (Phase 3)
3. **Updates:** sparse + `SyncToken`; refresh-on-5010-retry. (Phases 2–3)
4. **Minor version:** pin **75**. (All write/read calls)
5. **Limits:** ≤10 concurrent, ~500/min, batch ≤30 (and ≤120 batch-calls/min); 429 backoff-with-jitter + dead-letter. (Phase 3)
6. **Libraries:** `intuit-oauth` for OAuth, **httpx** for the API; not `python-quickbooks`. (Phases 1–4)
7. **Link-out:** generic QBO web-app link, **no report deep-links**; Reports API is the only supported in-app data path (CorePlus-metered). (Phase 5)
8. **Cost:** writes free, reads/CDC metered but far under the 500k/mo free tier; keep Phase-4 polling economical. (Phase 4)
9. **Historical data:** see §11 — recommended **archive + opening-balance migration**, pending owner sign-off. (Phase 5)

---

## 11. Historical-data handling (recommendation — needs owner sign-off)

Phase 5 drops the local GL tables, so existing books must be preserved first. **Recommended approach:**

1. **Archive for audit retention (do regardless):** export `journal_entry`, `journal_line`, `account`, `account_balance`,
   and a final **trial balance** snapshot as of the cutover date to durable storage (SQL dump + CSV), retained per the
   business's audit-retention policy. This is the system-of-record-of-last-resort and the down-migration recovery path.
2. **Seed QBO with opening balances, not full history:** post a single **cutover JournalEntry** (or per-account opening
   balances) into QBO as of the cutover date so QBO's balance sheet starts correct — rather than replaying years of
   transactions (costly, error-prone, and unnecessary for go-forward bookkeeping).

**Rationale:** replaying full history into QBO is high-risk and adds no audit value over the archive; opening balances +
archive gives correct go-forward books *and* a retained historical record. **Owner must confirm** (a) the retention period
and storage location, and (b) whether any prior-period detail must live *in QBO* (if so, a scoped historical import becomes
its own task). This decision unblocks the Phase 5 decommission gate.

---

## Appendix — source URLs

- OAuth 2.0 (tokens, scope, rotation, endpoints): `https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0`
- Discovery JSON: `https://developer.api.intuit.com/.well-known/openid_configuration/` · `…/openid_sandbox_configuration/`
- Entity references: `https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/<entity>` (journalentry, invoice, payment, bill, billpayment, customer, vendor, item, account, salesreceipt, creditmemo, vendorcredit, batch)
- RequestId idempotency: `https://help.developer.intuit.com/s/article/What-is-RequestId-and-its-usage`
- Error 5010 (stale SyncToken): `https://help.developer.intuit.com/s/article/QuickBooks-Online-API-Error-Code-5010`
- Limits/throttling: `https://help.developer.intuit.com/s/article/API-call-limits-and-throttling` · Best practices: `…/QuickBooks-Online-API-Best-Practices`
- Minor versions: `https://developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api/minor-versions` · blog `https://blogs.a.intuit.com/2025/01/21/changes-to-our-accounting-api-that-may-impact-your-application/`
- Batch cap / API changes: `https://blogs.intuit.com/2025/08/13/upcoming-changes-to-the-accounting-api/`
- Reports API: `https://developer.intuit.com/app/developer/qbo/docs/workflows/run-reports` · SDK class list `https://static.developer.intuit.com/sdkdocs/qbv3doc/ippdotnetdevkitv3/html/61d00e34-cb3b-478c-ba26-aae29766346d.htm`
- CDC: `https://developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api/change-data-capture`
- Webhooks + CloudEvents migration: `https://developer.intuit.com/app/developer/qbo/docs/develop/webhooks` · `https://blogs.intuit.com/2025/11/12/upcoming-change-to-webhooks-payload-structure`
- Go-live / production keys: `https://developer.intuit.com/app/developer/qbo/docs/go-live/publish-app/platform-requirements` · app-assessment FAQ `https://help.developer.intuit.com/s/article/New-app-assessment-process-FAQ`
- Cost / App Partner Program: `https://developer.intuit.com/app/developer/qbo/docs/get-started/partner-faq`
- Libraries: `https://pypi.org/project/intuit-oauth/` · `https://github.com/intuit/oauth-pythonclient` · `https://pypi.org/project/python-quickbooks/` · `https://github.com/ej2/python-quickbooks`

*Note: several Intuit pages are JS-rendered; token/scope/rotation values in §1 were extracted by rendering the live OAuth 2.0 page in a browser. Items marked **(corroborated)** rely on Intuit-controlled channels (blog/SDK) where the canonical page would not render to text.*
