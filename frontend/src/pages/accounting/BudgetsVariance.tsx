/**
 * Full variance report — sortable by variance % or absolute variance.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type AccountingPeriodResponse =
  components["schemas"]["AccountingPeriodResponse"];
type BudgetVarianceRow = components["schemas"]["BudgetVarianceRow"];

type SortKey = "variance_abs" | "variance_pct";

export function BudgetsVariancePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const periodId = searchParams.get("period_id") ?? "";
  const [periods, setPeriods] = useState<AccountingPeriodResponse[]>([]);
  const [rows, setRows] = useState<BudgetVarianceRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("variance_abs");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    let cancelled = false;
    api
      .get("/api/v1/accounting/periods")
      .then((res) => {
        if (cancelled) return;
        setPeriods(res.data.items);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!periodId) {
      setRows([]);
      return;
    }
    let cancelled = false;
    setError(null);
    api
      .get("/api/v1/accounting/budgets/variance", {
        params: { period_id: periodId },
      })
      .then((res) => {
        if (cancelled) return;
        setRows(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load variance.";
        setError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [periodId]);

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const va =
        sortKey === "variance_abs"
          ? Math.abs(Number(a.variance))
          : Number(a.variance_pct);
      const vb =
        sortKey === "variance_abs"
          ? Math.abs(Number(b.variance))
          : Number(b.variance_pct);
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  function updatePeriod(id: string) {
    const next = new URLSearchParams(searchParams);
    if (id) next.set("period_id", id);
    else next.delete("period_id");
    setSearchParams(next);
  }

  function setSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Variance report</h1>
        <Button asChild variant="outline">
          <Link to="/accounting/budgets">Back to budgets</Link>
        </Button>
      </header>

      <label className="flex flex-col gap-1 text-xs font-medium">
        Period
        <select
          className="h-9 w-64 rounded-md border border-input bg-background px-2 text-sm"
          value={periodId}
          onChange={(e) => updatePeriod(e.target.value)}
          data-testid="variance-period-select"
        >
          <option value="">— select period —</option>
          {periods.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.state})
            </option>
          ))}
        </select>
      </label>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2">Division</th>
            <th className="py-2 pr-2 text-right">Budget</th>
            <th className="py-2 pr-2 text-right">Actual</th>
            <th className="py-2 pr-2 text-right">
              <button
                type="button"
                onClick={() => setSort("variance_abs")}
                data-testid="sort-variance"
                className="uppercase tracking-wide hover:underline"
              >
                Variance{" "}
                {sortKey === "variance_abs"
                  ? sortDir === "asc"
                    ? "▲"
                    : "▼"
                  : ""}
              </button>
            </th>
            <th className="py-2 pr-2 text-right">
              <button
                type="button"
                onClick={() => setSort("variance_pct")}
                data-testid="sort-variance-pct"
                className="uppercase tracking-wide hover:underline"
              >
                %{" "}
                {sortKey === "variance_pct"
                  ? sortDir === "asc"
                    ? "▲"
                    : "▼"
                  : ""}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No data.
              </td>
            </tr>
          ) : (
            sorted.map((row) => (
              <tr
                key={`${row.account_id}-${row.division_id ?? "all"}`}
                className="border-b border-border/40"
              >
                <td className="py-1.5 pr-2">
                  <span className="font-mono text-xs">{row.account_code}</span>{" "}
                  {row.account_name}
                </td>
                <td className="py-1.5 pr-2 text-xs">
                  {row.division_name ?? "All"}
                </td>
                <td className="py-1.5 pr-2 text-right tabular-nums">
                  {Number(row.budget_amount).toFixed(2)}
                </td>
                <td className="py-1.5 pr-2 text-right tabular-nums">
                  {Number(row.actual_amount).toFixed(2)}
                </td>
                <td className="py-1.5 pr-2 text-right tabular-nums">
                  {Number(row.variance).toFixed(2)}
                </td>
                <td className="py-1.5 pr-2 text-right tabular-nums text-xs">
                  {row.variance_pct}%
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
