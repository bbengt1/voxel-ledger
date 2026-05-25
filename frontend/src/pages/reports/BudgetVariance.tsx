/**
 * `/reports/budget-variance` — budget vs actual per account
 * (Parity #227). Period picker fed by GET /api/v1/accounting-periods;
 * over-budget rows highlighted red, under-budget green.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type ReportResponse = components["schemas"]["BudgetVarianceResponse"];
type Row = components["schemas"]["BudgetVarianceRowResponse"];
type AccountingPeriod = components["schemas"]["AccountingPeriodResponse"];

const HIGHLIGHT_THRESHOLD_PCT = 10;

function rowClass(section: string, variancePct: string | null): string {
  if (variancePct === null) return "";
  const pct = Number(variancePct);
  if (Math.abs(pct) < HIGHLIGHT_THRESHOLD_PCT) return "";
  // For expenses: actual > budget is BAD (over). For revenue: actual < budget is BAD (under).
  const over = pct > 0;
  if (section === "revenue") {
    return over ? "bg-green-50" : "bg-red-50";
  }
  return over ? "bg-red-50" : "bg-green-50";
}

function Section({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <>
      <tr className="border-t border-border bg-muted/30">
        <td colSpan={6} className="py-1 px-2 text-xs uppercase font-medium">
          {title}
        </td>
      </tr>
      {rows.length === 0 ? (
        <tr>
          <td colSpan={6} className="py-1 px-2 text-muted-foreground">
            (no activity)
          </td>
        </tr>
      ) : (
        rows.map((r) => (
          <tr
            key={r.account_id}
            className={`border-b border-border/30 ${rowClass(r.section, r.variance_pct ?? null)}`}
          >
            <td className="py-1 px-2 font-mono text-xs">{r.code}</td>
            <td className="py-1 px-2">{r.name}</td>
            <td className="py-1 px-2 text-right tabular-nums">{r.budget}</td>
            <td className="py-1 px-2 text-right tabular-nums">{r.actual}</td>
            <td className="py-1 px-2 text-right tabular-nums">{r.variance}</td>
            <td
              className="py-1 px-2 text-right tabular-nums"
              data-testid={`bv-pct-${r.account_id}`}
            >
              {r.variance_pct === null ? "—" : `${r.variance_pct}%`}
            </td>
          </tr>
        ))
      )}
    </>
  );
}

function TotalRow({
  label,
  budget,
  actual,
}: {
  label: string;
  budget: string;
  actual: string;
}) {
  const variance = (Number(actual) - Number(budget)).toFixed(2);
  return (
    <tr className="border-t border-border bg-muted/20 font-semibold">
      <td colSpan={2} className="py-1 px-2 text-xs uppercase">
        {label}
      </td>
      <td className="py-1 px-2 text-right tabular-nums">{budget}</td>
      <td className="py-1 px-2 text-right tabular-nums">{actual}</td>
      <td className="py-1 px-2 text-right tabular-nums">{variance}</td>
      <td className="py-1 px-2"></td>
    </tr>
  );
}

export function BudgetVariancePage() {
  const [params, setParams] = useSearchParams();
  const periodId = params.get("period_id") ?? "";

  const [periods, setPeriods] = useState<AccountingPeriod[]>([]);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  useEffect(() => {
    api
      .get("/api/v1/accounting-periods")
      .then((res) => {
        const items = (res.data as { items?: AccountingPeriod[] }).items ?? [];
        setPeriods(items);
        // Auto-pick the first open period when nothing is selected.
        if (!periodId && items.length > 0) {
          updateParam("period_id", items[0]!.id);
        }
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!periodId) return;
    setError(null);
    api
      .get("/api/v1/reports/budget-variance", {
        params: { period_id: periodId },
      })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [periodId]);

  async function downloadCsv() {
    if (!periodId) return;
    const res = await apiClient.get("/api/v1/reports/budget-variance", {
      params: { period_id: periodId, format: "csv" },
      responseType: "blob",
    });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "budget-variance.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Budget vs actual</h1>
        <Button onClick={downloadCsv} data-testid="bv-csv" disabled={!report}>
          Download CSV
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label className="block text-xs">
          Period
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={periodId}
            onChange={(e) => updateParam("period_id", e.target.value)}
            data-testid="bv-period"
          >
            <option value="">— select —</option>
            {periods.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.start_date} → {p.end_date})
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      {report ? (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30 text-xs uppercase">
              <th className="py-1 px-2 text-left">Code</th>
              <th className="py-1 px-2 text-left">Account</th>
              <th className="py-1 px-2 text-right">Budget</th>
              <th className="py-1 px-2 text-right">Actual</th>
              <th className="py-1 px-2 text-right">Variance</th>
              <th className="py-1 px-2 text-right">Variance %</th>
            </tr>
          </thead>
          <tbody>
            <Section title="Revenue" rows={report.revenue_rows} />
            <TotalRow
              label="Total revenue"
              budget={String(report.total_revenue_budget)}
              actual={String(report.total_revenue_actual)}
            />
            <Section title="Cost of goods sold" rows={report.cogs_rows} />
            <TotalRow
              label="Total COGS"
              budget={String(report.total_cogs_budget)}
              actual={String(report.total_cogs_actual)}
            />
            <Section
              title="Operating expenses"
              rows={report.operating_expense_rows}
            />
            <TotalRow
              label="Total operating expenses"
              budget={String(report.total_operating_expense_budget)}
              actual={String(report.total_operating_expense_actual)}
            />
          </tbody>
        </table>
      ) : null}
    </section>
  );
}
