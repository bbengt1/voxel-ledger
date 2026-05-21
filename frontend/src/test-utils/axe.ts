/**
 * Vitest helper for axe-core (Phase 12.3a, #205).
 *
 * Each primary-flow test renders the page, waits for any async data
 * to settle, then calls ``expectNoA11yViolations(container)``. axe
 * runs the WCAG 2.1 AA rule set; failures are reported as a single
 * assertion with a readable formatter so the diff actually points
 * at the offending element.
 */
import axe, { type AxeResults, type Result } from "axe-core";
import { expect } from "vitest";

const RULESETS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

function formatViolation(v: Result): string {
  const nodes = v.nodes
    .slice(0, 3)
    .map((n) => `    selector: ${n.target.join(" ")}\n    html: ${n.html}`)
    .join("\n");
  return [
    `  [${v.impact}] ${v.id}: ${v.help}`,
    `    ${v.helpUrl}`,
    nodes,
    v.nodes.length > 3 ? `    ...+${v.nodes.length - 3} more nodes` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

export async function runAxe(container: Element): Promise<AxeResults> {
  return axe.run(container, {
    runOnly: { type: "tag", values: RULESETS },
    resultTypes: ["violations"],
    // jsdom doesn't ship canvas; the color-contrast rule needs it
    // to read pixel colors. Disable here and cover contrast in the
    // 12.3b manual + Storybook pass.
    rules: { "color-contrast": { enabled: false } },
  });
}

export async function expectNoA11yViolations(container: Element): Promise<void> {
  const result = await runAxe(container);
  if (result.violations.length === 0) {
    expect(result.violations).toEqual([]);
    return;
  }
  const message = [
    `axe-core found ${result.violations.length} violation(s):`,
    ...result.violations.map(formatViolation),
  ].join("\n");
  // Use a single assertion with a readable message; the array of
  // violations is the actual diff payload.
  expect(result.violations, message).toEqual([]);
}
