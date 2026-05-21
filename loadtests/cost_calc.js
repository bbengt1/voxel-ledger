// Live cost-calc (Phase 12.1, #203). Budget: p95 < 200ms.
//
//   k6 run loadtests/cost_calc.js
//
// Pure compute (no DB writes). We pass an inline plate spec so we
// don't need a seeded job; the only DB touch is reading rates and
// (optionally) material costs.

import http from "k6/http";
import { sleep } from "k6";
import { assertOk, authHeaders, defaultOptions, login, url } from "./_helpers.js";

const BODY = JSON.stringify({
  inputs: {
    plates: [
      {
        parts_per_set: 4,
        print_minutes: 120,
        setup_minutes: 5,
        print_grams_by_material: {},
        assigned_printer_ids: [],
      },
    ],
    quantity_ordered: 10,
  },
});

export const options = {
  ...defaultOptions("cost_calc"),
  thresholds: {
    http_req_duration: ["p(95)<200"],
    "http_req_failed": ["rate<0.01"],
  },
};

export function setup() {
  return { token: login() };
}

export default function (data) {
  const hdrs = {
    headers: {
      Authorization: `Bearer ${data.token}`,
      "Content-Type": "application/json",
    },
  };
  const res = http.post(url("/api/v1/jobs/calculate"), BODY, hdrs);
  assertOk(res, "/api/v1/jobs/calculate");
  sleep(0.1);
}
