// Shared k6 helpers (Phase 12.1, #203).
//
// One module so every test script logs in once, reuses the access
// token across iterations, and reads the budget config from env so
// CI can dial VUs/duration without touching the scripts.

import http from "k6/http";
import { check, fail } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const EMAIL = __ENV.OWNER_EMAIL || "owner@voxel.local";
const PASSWORD = __ENV.OWNER_PASSWORD || "voxel-owner-password";

export function defaultOptions(scenario) {
  const vus = parseInt(__ENV.VUS || "10", 10);
  const duration = __ENV.DURATION || "30s";
  return {
    scenarios: {
      [scenario]: {
        executor: "constant-vus",
        vus,
        duration,
      },
    },
    summaryTrendStats: ["min", "med", "avg", "p(95)", "p(99)", "max"],
  };
}

export function login() {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" } },
  );
  if (res.status !== 200) {
    fail(`login failed: status=${res.status} body=${res.body}`);
  }
  return res.json("access_token");
}

export function authHeaders(token) {
  return { headers: { Authorization: `Bearer ${token}` } };
}

export function url(path) {
  return `${BASE_URL}${path}`;
}

export function assertOk(res, label) {
  check(res, {
    [`${label}: 200`]: (r) => r.status === 200,
  });
}
