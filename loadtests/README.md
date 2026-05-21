# Load tests (Phase 12.1, #203)

[k6](https://k6.io) scripts that enforce the perf budgets from
[`IMPLEMENTATION_PLAN.md §6`](../print-sales-v2/IMPLEMENTATION_PLAN.md).
Each script ends with a k6 threshold; a missed budget fails the
process exit code, which CI treats as a build break.

## Budgets

| Script | Budget | Notes |
| --- | --- | --- |
| [`simple_get.js`](./simple_get.js) | **p95 < 200ms** | `/auth/me`, accounts list, dashboard KPIs |
| [`list_endpoints.js`](./list_endpoints.js) | **p95 < 400ms** | sales/invoices/bills/products/customers list, default `limit=50` |
| [`cost_calc.js`](./cost_calc.js) | **p95 < 200ms** | `POST /jobs/calculate` with inline plate spec |
| [`pos_lookup.js`](./pos_lookup.js) | **p95 < 500ms** | `GET /products/lookup?code=...` |

## Run locally

```bash
brew install k6                          # or follow https://k6.io/docs/get-started/installation/
make up                                  # backend on :8000
make seed                                # owner user (writes .env.dev)

# All four, defaults: 10 VUs for 30s, against http://localhost:8000
for f in loadtests/*.js; do
  [[ $f == */_helpers.js ]] && continue
  k6 run "$f"
done
```

Tune at the command line — every script reads from env:

```bash
BASE_URL=http://localhost:8000 \
  VUS=50 DURATION=2m \
  OWNER_EMAIL=$(grep ^OWNER_EMAIL .env.dev | cut -d= -f2) \
  OWNER_PASSWORD=$(grep ^OWNER_PASSWORD .env.dev | cut -d= -f2) \
  k6 run loadtests/simple_get.js
```

## Seed data

Local stacks are mostly empty; meaningful load-test runs want a
representative dataset:

- **1k products** with rotating SKUs `SKU-00001..SKU-01000` (so
  `pos_lookup.js` can hit a hot product).
- **10k sales** spread across 12 months (so list pagination is
  exercised, not just an empty table scan).
- **100k inventory transactions** (so `inventory_on_hand` is
  realistic when listing).

A seed script for the above is intentionally out of scope here — wire
it into the Phase 12.2 (#204) backup-drill prep, since the same
synthetic dataset feeds the restore-parity smoke check. Until that
ships, run the scripts against whatever your dev stack already has;
the latency budgets still apply.

## CI

The `loadtests-smoke` job in `.github/workflows/ci.yml` runs each
script at `VUS=10 DURATION=30s` against a freshly-seeded backend
(owner-only data, no synthetic load). It enforces only the latency
threshold — not the seed-data assumptions — so it fails loudly on a
hot-path regression without needing a giant fixture.

A nightly perf-regression workflow (with the full seed) is a Phase
12 follow-up, not in this PR.

## Adding a new script

Copy [`simple_get.js`](./simple_get.js) as a template:

```js
import { assertOk, authHeaders, defaultOptions, login, url } from "./_helpers.js";

export const options = {
  ...defaultOptions("<scenario-name>"),
  thresholds: {
    http_req_duration: ["p(95)<<budget-ms>"],
    "http_req_failed": ["rate<0.01"],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  const res = http.get(url("<endpoint>"), authHeaders(data.token));
  assertOk(res, "<endpoint>");
}
```

Wire it into the smoke job in `.github/workflows/ci.yml` so CI keeps
honest.
