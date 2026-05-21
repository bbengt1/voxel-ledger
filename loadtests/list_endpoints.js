// List endpoints (Phase 12.1, #203). Budget: p95 < 400ms.
//
//   k6 run loadtests/list_endpoints.js
//
// Default limit=50 — same defaults the UI uses. Seeded against a
// 10k-sale dataset (see loadtests/README.md §Seed).

import http from "k6/http";
import { sleep } from "k6";
import { assertOk, authHeaders, defaultOptions, login, url } from "./_helpers.js";

const ENDPOINTS = [
  "/api/v1/sales?limit=50",
  "/api/v1/invoices?limit=50",
  "/api/v1/bills?limit=50",
  "/api/v1/products?limit=50",
  "/api/v1/customers?limit=50",
];

export const options = {
  ...defaultOptions("list_endpoints"),
  thresholds: {
    http_req_duration: ["p(95)<400"],
    "http_req_failed": ["rate<0.01"],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  const path = ENDPOINTS[Math.floor(Math.random() * ENDPOINTS.length)];
  const res = http.get(url(path), authHeaders(data.token));
  assertOk(res, path);
  sleep(0.1);
}
