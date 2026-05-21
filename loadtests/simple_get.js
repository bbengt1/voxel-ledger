// Simple GETs (Phase 12.1, #203). Budget: p95 < 200ms.
//
//   k6 run loadtests/simple_get.js
//
// Hits a small rotation of index-covered, no-N+1 endpoints. Failing
// the threshold fails the k6 exit code, which the CI smoke job
// treats as a budget breach.

import http from "k6/http";
import { sleep } from "k6";
import { assertOk, authHeaders, defaultOptions, login, url } from "./_helpers.js";

const ENDPOINTS = [
  "/api/v1/auth/me",
  "/api/v1/accounts?limit=1",
  "/api/v1/dashboard/kpis",
];

export const options = {
  ...defaultOptions("simple_get"),
  thresholds: {
    http_req_duration: ["p(95)<200"],
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
