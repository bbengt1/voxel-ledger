/**
 * `/reports/balance-sheet` — assets / liabilities / equity as of a date
 * (Phase 10.8a, #183). Imbalance pill renders when the residual is non-zero.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["BalanceSheetResponse"];
type Row = components["schemas"]["BalanceSheetRowResponse"];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
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
            (no balance)
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
            <td className="py-1 px-2 text-right tabular-nums">{r.balance}</td>
          </tr>
        ))
      )}
    </>
  );
}

export function BalanceSheetPage() {
  const [params, setParams] = useSearchParams();
  const asOf = params.get("as_of") ?? todayIso();
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
    const q: Record<string, string> = { as_of: asOf };
    if (divisionId) q["division_id"] = divisionId;
    api
      .get("/api/v1/reports/balance-sheet", { params: q })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [asOf, divisionId]);

  async function downloadCsv() {
    const q: Record<string, string> = { as_of: asOf, format: "csv" };
    if (divisionId) q["division_id"] = divisionId;
    const res = await apiClient.get("/api/v1/reports/balance-sheet", {
      params: q,
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `balance-sheet-${asOf}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const imbalanced = report && report.imbalance !== "0.00";

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Balance sheet</h1>
        <Button onClick={downloadCsv} data-testid="bs-csv">
          Download CSV
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block text-xs">
          As of
          <Input
            type="date"
            value={asOf}
            onChange={(e) => updateParam("as_of", e.target.value)}
            data-testid="bs-as-of"
          />
        </label>
        <label className="block text-xs">
          Division
          <Input
            value={divisionId}
            onChange={(e) => updateParam("division_id", e.target.value)}
            placeholder="(all divisions)"
            data-testid="bs-division"
          />
        </label>
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {imbalanced ? (
        <div
          role="alert"
          className="rounded border border-yellow-500 bg-yellow-500/10 p-3 text-sm"
          data-testid="bs-imbalance"
        >
          Imbalance: <span className="font-mono">{report?.imbalance}</span> —
          set <code>reports.retained_earnings_account_id</code> or close P&amp;L to
          retained earnings to clear this.
        </div>
      ) : null}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[24rem] border-collapse text-sm">
        <tbody>
          {report ? (
            <>
              <Section title="Assets" rows={report.asset_rows} />
              <tr className="border-t-2 border-border font-semibold">
                <td className="py-1 px-2">Total assets</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.total_assets}
                </td>
              </tr>
              <Section title="Liabilities" rows={report.liability_rows} />
              <tr className="border-t border-border font-medium">
                <td className="py-1 px-2">Total liabilities</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.total_liabilities}
                </td>
              </tr>
              <Section title="Equity" rows={report.equity_rows} />
              <tr className="border-t border-border font-medium">
                <td className="py-1 px-2">Total equity</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.total_equity}
                </td>
              </tr>
              <tr className="border-t-2 border-primary font-semibold">
                <td className="py-1 px-2">Liabilities + equity</td>
                <td className="py-1 px-2 text-right tabular-nums">
                  {report.total_liabilities_and_equity}
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
