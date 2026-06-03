/**
 * `/reports/trial-balance` — opening + period activity + closing per
 * account, sorted by code. Grand-total row asserts Σ debit == Σ credit
 * (Phase 10.8a, #183).
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["TrialBalanceResponse"];

function defaultRange() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: today.toISOString().slice(0, 10),
  };
}

export function TrialBalancePage() {
  const [params, setParams] = useSearchParams();
  const defaults = defaultRange();
  const dateFrom = params.get("date_from") ?? defaults.date_from;
  const dateTo = params.get("date_to") ?? defaults.date_to;
  const divisionId = params.get("division_id") ?? "";
  const includeZero = params.get("include_zero") === "true";

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
    if (includeZero) q["include_zero"] = "true";
    api
      .get("/api/v1/reports/trial-balance", { params: q })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [dateFrom, dateTo, divisionId, includeZero]);

  async function downloadCsv() {
    const q: Record<string, string> = {
      date_from: dateFrom,
      date_to: dateTo,
      format: "csv",
    };
    if (divisionId) q["division_id"] = divisionId;
    if (includeZero) q["include_zero"] = "true";
    const res = await apiClient.get("/api/v1/reports/trial-balance", {
      params: q,
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trial-balance-${dateFrom}-to-${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const balanced =
    report && report.total_period_debit === report.total_period_credit;

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Trial balance</h1>
        <Button onClick={downloadCsv} data-testid="tb-csv">
          Download CSV
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block text-xs">
          From
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParam("date_from", e.target.value)}
            data-testid="tb-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="tb-to"
          />
        </label>
        <label className="block text-xs">
          Division
          <Input
            value={divisionId}
            onChange={(e) => updateParam("division_id", e.target.value)}
            placeholder="(all)"
            data-testid="tb-division"
          />
        </label>
        <label className="mt-5 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeZero}
            onChange={(e) => updateParam("include_zero", e.target.checked ? "true" : "")}
            data-testid="tb-include-zero"
          />
          Include zero-activity accounts
        </label>
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {report && !balanced ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
          data-testid="tb-unbalanced"
        >
          Σ debit ≠ Σ credit — the ledger is out of balance for this window.
        </div>
      ) : null}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[48rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Code</th>
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2 text-right">Opening</th>
            <th className="py-2 pr-2 text-right">Period debit</th>
            <th className="py-2 pr-2 text-right">Period credit</th>
            <th className="py-2 pr-2 text-right">Closing</th>
          </tr>
        </thead>
        <tbody>
          {report && report.rows.length ? (
            report.rows.map((r) => (
              <tr key={r.account_id} className="border-b border-border/30">
                <td className="py-1 pr-2 font-mono text-xs">{r.code}</td>
                <td className="py-1 pr-2">{r.name}</td>
                <td className="py-1 pr-2 text-right tabular-nums">
                  {r.opening_balance}
                </td>
                <td className="py-1 pr-2 text-right tabular-nums">
                  {r.period_debit}
                </td>
                <td className="py-1 pr-2 text-right tabular-nums">
                  {r.period_credit}
                </td>
                <td className="py-1 pr-2 text-right tabular-nums font-medium">
                  {r.closing_balance}
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No activity in this window.
              </td>
            </tr>
          )}
        </tbody>
        {report ? (
          <tfoot>
            <tr className="border-t-2 border-primary font-semibold">
              <td className="py-2 pr-2" colSpan={3}>
                GRAND TOTAL
              </td>
              <td className="py-2 pr-2 text-right tabular-nums">
                {report.total_period_debit}
              </td>
              <td className="py-2 pr-2 text-right tabular-nums">
                {report.total_period_credit}
              </td>
              <td />
            </tr>
          </tfoot>
        ) : null}
      </table>
      </div>
    </section>
  );
}
