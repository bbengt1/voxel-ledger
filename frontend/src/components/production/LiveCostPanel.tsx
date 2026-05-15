/**
 * Live cost panel — renders the latest `CalcResultResponse` payload from
 * `POST /api/v1/jobs/calculate`. The parent owns the debouncing/in-flight
 * state; this component just renders. Doherty-threshold target: <400ms
 * round-trip feedback, with a small spinner during in-flight requests.
 */
import { useState } from "react";

import type { components } from "@/api/types";

type CalcResult = components["schemas"]["CalcResultResponse"];

interface Props {
  result: CalcResult | null;
  loading: boolean;
  error: string | null;
}

function fmtMoney(s: string | null | undefined): string {
  if (!s) return "—";
  const n = Number.parseFloat(s);
  if (Number.isNaN(n)) return s;
  return `$${n.toFixed(2)}`;
}

export function LiveCostPanel({ result, loading, error }: Props) {
  const [showPlates, setShowPlates] = useState(false);

  return (
    <aside
      aria-label="Live cost estimate"
      data-testid="live-cost-panel"
      className="sticky top-6 flex w-80 flex-col gap-3 rounded-lg border border-border bg-muted/30 p-4"
    >
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Live cost
        </h2>
        {loading ? (
          <span
            data-testid="cost-spinner"
            role="status"
            aria-label="Recalculating"
            className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent"
          />
        ) : null}
      </header>

      {error ? (
        <p
          role="alert"
          data-testid="cost-error"
          className="text-xs text-destructive"
        >
          {error}
        </p>
      ) : null}

      {result ? (
        <>
          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Pieces / set</dt>
            <dd className="text-right" data-testid="cost-pieces-per-set">
              {result.pieces_per_set}
            </dd>
            <dt className="text-muted-foreground">Sets required</dt>
            <dd className="text-right" data-testid="cost-sets-required">
              {result.sets_required}
            </dd>
          </dl>

          <hr className="border-border" />

          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Material</dt>
            <dd className="text-right">{fmtMoney(result.material_cost)}</dd>
            <dt className="text-muted-foreground">Supply</dt>
            <dd className="text-right">{fmtMoney(result.supply_cost)}</dd>
            <dt className="text-muted-foreground">Labor</dt>
            <dd className="text-right">{fmtMoney(result.labor_cost)}</dd>
            <dt className="text-muted-foreground">Machine</dt>
            <dd className="text-right">{fmtMoney(result.machine_cost)}</dd>
            <dt className="text-muted-foreground">Overhead</dt>
            <dd className="text-right">{fmtMoney(result.overhead_cost)}</dd>
            <dt className="font-semibold">Total</dt>
            <dd
              className="text-right font-semibold"
              data-testid="cost-total"
            >
              {fmtMoney(result.total_cost)}
            </dd>
          </dl>

          <hr className="border-border" />

          <div className="rounded-md bg-background p-2">
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-muted-foreground">Cost / piece</span>
              <span
                className="text-base font-semibold"
                data-testid="cost-per-piece"
              >
                {fmtMoney(result.cost_per_piece)}
              </span>
            </div>
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-muted-foreground">Suggested price</span>
              <span
                className="text-base font-semibold"
                data-testid="cost-suggested-price"
              >
                {fmtMoney(result.suggested_unit_price)}
              </span>
            </div>
          </div>

          {result.per_plate.length > 0 ? (
            <details
              className="text-xs"
              open={showPlates}
              onToggle={(e) => setShowPlates((e.target as HTMLDetailsElement).open)}
            >
              <summary className="cursor-pointer select-none text-muted-foreground">
                Per-plate breakdown ({result.per_plate.length})
              </summary>
              <ul className="mt-2 space-y-1">
                {result.per_plate.map((p) => (
                  <li
                    key={p.plate_index}
                    className="rounded border border-border p-1.5"
                    data-testid={`cost-plate-${p.plate_index}`}
                  >
                    <div className="flex justify-between">
                      <span>Plate #{p.plate_index + 1}</span>
                      <span>{p.runs} runs</span>
                    </div>
                    <div className="text-muted-foreground">
                      M {fmtMoney(p.material_cost)} · L{" "}
                      {fmtMoney(p.labor_cost)} · Mh{" "}
                      {fmtMoney(p.machine_cost)}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : (
        <p className="text-xs text-muted-foreground" data-testid="cost-empty">
          Add at least one plate with print time and filament to see a cost
          estimate.
        </p>
      )}
    </aside>
  );
}
