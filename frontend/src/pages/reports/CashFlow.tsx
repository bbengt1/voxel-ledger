/**
 * `/reports/cash-flow` — indirect-method cash flow report
 * (Phase 10.8a, #183). Surfaces the reconciliation residual.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["CashFlowResponse"];
type Line = components["schemas"]["CashFlowLineResponse"];

function defaultRange() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: today.toISOString().slice(0, 10),
  };
}

function Section({ title, lines, total }: { title: string; lines: Line[]; total: string }) {
  return (
    <>
      <tr className="border-t border-border bg-muted/30">
        <td colSpan={2} className="py-1 px-2 text-xs uppercase font-medium">
          {title}
        </td>
      </tr>
      {lines.length === 0 ? (
        <tr>
          <td className="py-1 px-2 text-muted-foreground" colSpan={2}>
            (no activity)
          </td>
        </tr>
      ) : (
        lines.map((line, i) => (
          <tr key={i} className="border-b border-border/30">
            <td className="py-1 px-2">{line.line_item}</td>
            <td className="py-1 px-2 text-right tabular-nums">{line.amount}</td>
          </tr>
        ))
      )}
      <tr className="border-t border-border font-medium">
        <td className="py-1 px-2">Net {title}</td>
        <td className="py-1 px-2 text-right tabular-nums">{total}</td>
      </tr>
    </>
  );
}

export function CashFlowPage() {
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
      .get("/api/v1/reports/cash-flow", { params: q })
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
    const res = await apiClient.get("/api/v1/reports/cash-flow", {
      params: q,
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cash-flow-${dateFrom}-to-${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const hasResidual =
    report && report.reconciliation_residual !== "0.00";

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Cash flow (indirect)</h1>
        <Button onClick={downloadCsv} data-testid="cf-csv">
          Download CSV
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block text-xs">
          From
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParam("date_from", e.target.value)}
            data-testid="cf-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="cf-to"
          />
        </label>
        <label className="block text-xs">
          Division
          <Input
            value={divisionId}
            onChange={(e) => updateParam("division_id", e.target.value)}
            placeholder="(all divisions)"
            data-testid="cf-division"
          />
        </label>
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {hasResidual ? (
        <div
          role="alert"
          className="rounded border border-yellow-500 bg-yellow-500/10 p-3 text-sm"
          data-testid="cf-residual"
        >
          Reconciliation residual:{" "}
          <span className="font-mono">{report?.reconciliation_residual}</span>{" "}
          — check the ``reports.*_accounts`` settings for misclassified
          accounts.
        </div>
      ) : null}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[24rem] border-collapse text-sm">
        <tbody>
          {report ? (
            <>
              <Section
                title="Operating activities"
                lines={report.operating_lines}
                total={report.operating_total}
              />
              <Section
                title="Investing activities"
                lines={report.investing_lines}
                total={report.investing_total}
              />
              <Section
                title="Financing activities"
                lines={report.financing_lines}
                total={report.financing_total}
              />
              <tr className="border-t-2 border-primary font-bold">
                <td className="py-1 px-2">Net change in cash</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.net_change_in_cash}
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
      </div>
    </section>
  );
}
