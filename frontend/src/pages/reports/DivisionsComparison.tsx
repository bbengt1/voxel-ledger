/**
 * `/reports/divisions-comparison` — per-division P&L side-by-side
 * (Parity #229). One column per active division plus a final
 * "(unallocated)" column for lines without a ``division_id``.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["DivisionsComparisonResponse"];
type Column = components["schemas"]["ComparisonColumnResponse"];
type Row = components["schemas"]["ComparisonRowResponse"];

function defaultRange() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: today.toISOString().slice(0, 10),
  };
}

function Section({
  title,
  rows,
  columns,
}: {
  title: string;
  rows: Row[];
  columns: Column[];
}) {
  return (
    <>
      <tr className="border-t border-border bg-muted/30">
        <td
          colSpan={columns.length + 2}
          className="py-1 px-2 text-xs uppercase font-medium"
        >
          {title}
        </td>
      </tr>
      {rows.length === 0 ? (
        <tr>
          <td
            colSpan={columns.length + 2}
            className="py-1 px-2 text-muted-foreground"
          >
            (no activity)
          </td>
        </tr>
      ) : (
        rows.map((r) => (
          <tr key={r.account_id} className="border-b border-border/30">
            <td className="py-1 px-2 font-mono text-xs">{r.code}</td>
            <td className="py-1 px-2">{r.name}</td>
            {columns.map((col) => (
              <td
                key={col.division_id}
                className="py-1 px-2 text-right tabular-nums"
              >
                {r.amounts[col.division_id] ?? "0.00"}
              </td>
            ))}
          </tr>
        ))
      )}
    </>
  );
}

function TotalRow({
  label,
  values,
  columns,
  emphasize,
}: {
  label: string;
  values: Record<string, string>;
  columns: Column[];
  emphasize?: boolean;
}) {
  return (
    <tr
      className={
        emphasize
          ? "border-t border-border bg-muted/20 font-semibold"
          : "border-t border-border/40"
      }
    >
      <td colSpan={2} className="py-1 px-2 text-xs uppercase">
        {label}
      </td>
      {columns.map((col) => (
        <td
          key={col.division_id}
          className="py-1 px-2 text-right tabular-nums"
        >
          {values[col.division_id] ?? "0.00"}
        </td>
      ))}
    </tr>
  );
}

export function DivisionsComparisonPage() {
  const [params, setParams] = useSearchParams();
  const defaults = defaultRange();
  const dateFrom = params.get("date_from") ?? defaults.date_from;
  const dateTo = params.get("date_to") ?? defaults.date_to;

  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  useEffect(() => {
    setError(null);
    api
      .get("/api/v1/reports/divisions-comparison", {
        params: { date_from: dateFrom, date_to: dateTo },
      })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [dateFrom, dateTo]);

  async function downloadCsv() {
    const res = await apiClient.get(
      "/api/v1/reports/divisions-comparison",
      {
        params: { date_from: dateFrom, date_to: dateTo, format: "csv" },
        responseType: "blob",
      },
    );
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "divisions-comparison.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Divisions comparison</h1>
        <Button onClick={downloadCsv} data-testid="dc-csv">
          Download CSV
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="block text-xs">
          From
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParam("date_from", e.target.value)}
            data-testid="dc-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="dc-to"
          />
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
        <div className="overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-xs uppercase">
                <th className="py-1 px-2 text-left">Code</th>
                <th className="py-1 px-2 text-left">Account</th>
                {report.columns.map((col) => (
                  <th
                    key={col.division_id}
                    className="py-1 px-2 text-right"
                    data-testid={`dc-col-${col.division_id}`}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <Section
                title="Revenue"
                rows={report.revenue_rows}
                columns={report.columns}
              />
              <TotalRow
                label="Total revenue"
                values={report.total_revenue as Record<string, string>}
                columns={report.columns}
              />
              <Section
                title="Cost of goods sold"
                rows={report.cogs_rows}
                columns={report.columns}
              />
              <TotalRow
                label="Gross profit"
                values={report.gross_profit as Record<string, string>}
                columns={report.columns}
              />
              <Section
                title="Operating expenses"
                rows={report.operating_expense_rows}
                columns={report.columns}
              />
              <TotalRow
                label="Operating income"
                values={report.operating_income as Record<string, string>}
                columns={report.columns}
              />
              <TotalRow
                label="Net income"
                values={report.net_income as Record<string, string>}
                columns={report.columns}
                emphasize
              />
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
