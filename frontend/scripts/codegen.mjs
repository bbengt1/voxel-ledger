#!/usr/bin/env node
/**
 * Frontend OpenAPI -> TypeScript codegen wrapper.
 *
 * Runs `openapi-typescript` against the committed `src/api/openapi.json`
 * and writes the result to `src/api/types.ts` with a generated-file header
 * prepended.
 *
 * Why a wrapper script instead of the bare CLI?
 * - Lets us prepend the "do not edit" header in a single place.
 * - Lets us normalize line endings so the output is byte-stable across
 *   platforms (the CI drift check relies on this).
 *
 * See docs/openapi-codegen.md.
 */

import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(here, "..");
const specPath = resolve(frontendRoot, "src/api/openapi.json");
const outPath = resolve(frontendRoot, "src/api/types.ts");

mkdirSync(dirname(outPath), { recursive: true });

const result = spawnSync(
  "pnpm",
  ["exec", "openapi-typescript", specPath, "-o", outPath],
  { cwd: frontendRoot, stdio: "inherit" },
);

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}

const header = [
  "// GENERATED — do not edit by hand.",
  "// Source: backend OpenAPI spec at /api/v1/openapi.json (see backend/app/main.py).",
  "// Regenerate types from the committed spec: `pnpm run codegen`.",
  "// Re-export the spec from the backend and regenerate:",
  "//   `pnpm run codegen:export && pnpm run codegen`.",
  "// CI enforces drift via `pnpm run codegen:check`.",
  "",
].join("\n");

const body = readFileSync(outPath, "utf8");
// Normalize trailing whitespace and ensure exactly one trailing newline so
// the file is byte-stable run-to-run.
const normalized = body.replace(/\r\n/g, "\n").replace(/\s+$/u, "") + "\n";
writeFileSync(outPath, header + normalized, "utf8");

console.log(`wrote ${outPath}`);
