// POS scan -> line lookup (Phase 12.1, #203). Budget: p95 < 500ms.
//
//   k6 run loadtests/pos_lookup.js
//
// Hits the GET /api/v1/products/lookup?code=<sku|upc> path the POS
// scanner calls between scan + line-add. Seed expects SKU rotation
// SKU-00001..SKU-01000 (see loadtests/README.md §Seed).

import http from "k6/http";
import { sleep } from "k6";
import { assertOk, authHeaders, defaultOptions, login, url } from "./_helpers.js";

const SKU_COUNT = parseInt(__ENV.SKU_COUNT || "1000", 10);

export const options = {
  ...defaultOptions("pos_lookup"),
  thresholds: {
    http_req_duration: ["p(95)<500"],
    // POS lookups against an empty seed will 404; allow up to 10%.
    "http_req_failed": ["rate<0.10"],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  const idx = 1 + Math.floor(Math.random() * SKU_COUNT);
  const code = "SKU-" + String(idx).padStart(5, "0");
  const res = http.get(
    url(`/api/v1/products/lookup?code=${encodeURIComponent(code)}`),
    authHeaders(data.token),
  );
  // 404 is acceptable on an un-seeded stack; we only enforce the
  // latency budget here.
  if (res.status !== 200 && res.status !== 404) {
    assertOk(res, "/api/v1/products/lookup");
  }
  sleep(0.1);
}
