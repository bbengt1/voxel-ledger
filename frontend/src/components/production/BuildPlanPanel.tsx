/**
 * Read-only panel showing a build's pre-flight: required parts/supplies
 * with on-hand availability + shortfalls, and the rolled-up cost
 * (components + assembly labor). Sourced from `POST /builds/preview` (new
 * build) or `GET /builds/{id}/plan` (existing build). Dumb component — the
 * parent owns fetching.
 */
import type { components } from "@/api/types";

type BuildPlan = components["schemas"]["BuildPlanResponse"];

interface Props {
  plan: BuildPlan | null;
  loading: boolean;
  error: string | null;
}

function fmtMoney(s: string | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const n = Number.parseFloat(s);
  if (Number.isNaN(n)) return s;
  return `$${n.toFixed(2)}`;
}

function fmtQty(s: string): string {
  const n = Number.parseFloat(s);
  if (Number.isNaN(n)) return s;
  // Trim trailing zeros for readability (6,1 → "6").
  return String(n);
}

export function BuildPlanPanel({ plan, loading, error }: Props) {
  return (
    <aside
      className="sticky top-6 h-fit w-80 shrink-0 rounded-lg border border-border p-4"
      data-testid="build-plan-panel"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Build plan</h2>
        {loading ? (
          <span data-testid="plan-spinner" className="text-xs text-muted-foreground">
            Calculating…
          </span>
        ) : null}
      </div>

      {error ? (
        <p
          role="alert"
          data-testid="plan-error"
          className="mt-2 rounded border border-destructive bg-destructive/10 p-2 text-xs text-destructive"
        >
          {error}
        </p>
      ) : null}

      {!plan ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Pick a product and quantity to see required components and cost.
        </p>
      ) : (
        <>
          <div
            className={`mt-3 rounded-md px-2 py-1 text-center text-xs font-medium ${
              plan.can_build
                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
                : "bg-destructive/10 text-destructive"
            }`}
            data-testid="plan-can-build"
          >
            {plan.can_build ? "Ready to build" : "Insufficient stock"}
          </div>

          <table className="mt-3 w-full table-fixed border-collapse text-xs">
            <thead>
              <tr className="border-b border-border text-left uppercase text-muted-foreground">
                <th className="py-1 pr-1">Component</th>
                <th className="py-1 pr-1 text-right">Need</th>
                <th className="py-1 pr-1 text-right">Have</th>
              </tr>
            </thead>
            <tbody>
              {(plan.lines ?? []).length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-2 text-center text-muted-foreground">
                    This product has no part/supply BOM.
                  </td>
                </tr>
              ) : (
                (plan.lines ?? []).map((line) => (
                  <tr
                    key={`${line.component_kind}:${line.component_id}`}
                    className="border-b border-border/40"
                    data-testid={`plan-line-${line.component_id}`}
                  >
                    <td className="py-1 pr-1">
                      <span className="block truncate" title={line.name}>
                        {line.name}
                      </span>
                      <span className="text-[10px] uppercase text-muted-foreground">
                        {line.component_kind}
                      </span>
                    </td>
                    <td className="py-1 pr-1 text-right tabular-nums">
                      {fmtQty(line.required_quantity)}
                    </td>
                    <td
                      className={`py-1 pr-1 text-right tabular-nums ${
                        line.sufficient ? "" : "font-semibold text-destructive"
                      }`}
                      data-testid={`plan-onhand-${line.component_id}`}
                    >
                      {fmtQty(line.on_hand)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          <dl className="mt-3 space-y-1 border-t border-border pt-3 text-xs">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Components</dt>
              <dd data-testid="plan-component-cost">{fmtMoney(plan.component_cost)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Assembly labor</dt>
              <dd data-testid="plan-labor-cost">{fmtMoney(plan.assembly_labor_cost)}</dd>
            </div>
            <div className="flex justify-between font-medium">
              <dt>Total</dt>
              <dd data-testid="plan-total-cost">{fmtMoney(plan.total_cost)}</dd>
            </div>
            <div className="flex justify-between text-muted-foreground">
              <dt>Per unit</dt>
              <dd data-testid="plan-unit-cost">{fmtMoney(plan.unit_cost)}</dd>
            </div>
          </dl>
        </>
      )}
    </aside>
  );
}
