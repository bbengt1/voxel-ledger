/**
 * `/reports/income-statement` — P&L report (Phase 10.8a, #183).
 *
 * Date-range + division filter; renders Revenue / COGS / Operating
 * expense sections with grand totals. CSV export via the same
 * endpoint with ``?format=csv``.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { SavedReportsControl } from "@/components/reports/SavedReportsControl";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["IncomeStatementResponse"];
type Row = components["schemas"]["IncomeStatementRowResponse"];

function defaultRange() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: today.toISOString().slice(0, 10),
  };
}

function indent(depth: number): React.CSSProperties {
  return { paddingLeft: `${Math.min(depth, 4) * 12}px` };
}

function Section({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <>
      <tr className="border-t border-border bg-muted/30">
        <td colSpan={2} className="py-1 px-2 text-xs uppercase font-medium">
          {title}
        </td>
      </tr>
      {rows.length === 0 ? (
        <tr>
          <td className="py-1 px-2 text-muted-foreground" colSpan={2}>
            (no activity)
          </td>
        </tr>
      ) : (
        rows.map((r) => (
          <tr key={r.account_id} className="border-b border-border/30">
            <td className="py-1 px-2" style={indent(r.depth)}>
              <span className="font-mono text-xs text-muted-foreground">
                {r.code}
              </span>{" "}
              {r.name}
            </td>
            <td className="py-1 px-2 text-right tabular-nums">{r.amount}</td>
          </tr>
        ))
      )}
    </>
  );
}

export function IncomeStatementPage() {
  const [params, setParams] = useSearchParams();
  const defaults = defaultRange();
  const dateFrom = params.get("date_from") ?? defaults.date_from;
  const dateTo = params.get("date_to") ?? defaults.date_to;
  const divisionId = params.get("division_id") ?? "";

  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  useEffect(() => {
    const q: Record<string, string> = { date_from: dateFrom, date_to: dateTo };
    if (divisionId) q["division_id"] = divisionId;
    api
      .get("/api/v1/reports/income-statement", { params: q })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [dateFrom, dateTo, divisionId]);

  async function downloadCsv() {
    const q: Record<string, string> = {
      date_from: dateFrom,
      date_to: dateTo,
      format: "csv",
    };
    if (divisionId) q["division_id"] = divisionId;
    const res = await apiClient.get("/api/v1/reports/income-statement", {
      params: q,
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `income-statement-${dateFrom}-to-${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Income statement (P&amp;L)</h1>
        <Button onClick={downloadCsv} data-testid="is-csv">
          Download CSV
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label className="block text-xs">
          From
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParam("date_from", e.target.value)}
            data-testid="is-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="is-to"
          />
        </label>
        <label className="block text-xs">
          Division
          <Input
            value={divisionId}
            onChange={(e) => updateParam("division_id", e.target.value)}
            placeholder="(all divisions)"
            data-testid="is-division"
          />
        </label>
      </div>

      <SavedReportsControl
        reportKind="income_statement"
        currentFilters={{
          date_from: dateFrom,
          date_to: dateTo,
          division_id: divisionId || null,
        }}
        onLoad={(filters) => {
          const next = new URLSearchParams(params);
          for (const [k, v] of Object.entries(filters)) {
            if (v == null || v === "") next.delete(k);
            else next.set(k, String(v));
          }
          setParams(next, { replace: true });
        }}
      />

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <tbody>
          {report ? (
            <>
              <Section title="Revenue" rows={report.revenue_rows} />
              <tr className="border-t border-border font-medium">
                <td className="py-1 px-2">Total revenue</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.total_revenue}
                </td>
              </tr>
              <Section title="Cost of goods sold" rows={report.cogs_rows} />
              <tr className="border-t border-border font-medium">
                <td className="py-1 px-2">Total COGS</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.total_cogs}
                </td>
              </tr>
              <tr className="border-t-2 border-border font-semibold">
                <td className="py-1 px-2">Gross profit</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.gross_profit}
                </td>
              </tr>
              <Section
                title="Operating expenses"
                rows={report.operating_expense_rows}
              />
              <tr className="border-t border-border font-medium">
                <td className="py-1 px-2">Total operating expenses</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.total_operating_expenses}
                </td>
              </tr>
              <tr className="border-t-2 border-border font-semibold">
                <td className="py-1 px-2">Operating income</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.operating_income}
                </td>
              </tr>
              <tr className="border-t-2 border-primary font-bold">
                <td className="py-1 px-2">Net income</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.net_income}
                </td>
              </tr>
            </>
          ) : (
            <tr>
              <td colSpan={2} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
