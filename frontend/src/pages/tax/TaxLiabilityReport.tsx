/**
 * `/reports/tax-liability` — sales-tax liability report (Phase 9.10b, #162).
 *
 * Bucketed per profile + rate over a date range. CSV export available.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["TaxLiabilityReportResponse"];
type TaxProfileResponse = components["schemas"]["TaxProfileResponse"];

function defaultRange() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth() - 2, 1);
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: today.toISOString().slice(0, 10),
  };
}

export function TaxLiabilityReportPage() {
  const [params, setParams] = useSearchParams();
  const defaults = defaultRange();
  const dateFrom = params.get("date_from") ?? defaults.date_from;
  const dateTo = params.get("date_to") ?? defaults.date_to;
  const profileId = params.get("profile_id") ?? "";

  const [profiles, setProfiles] = useState<TaxProfileResponse[]>([]);
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
      .get("/api/v1/tax-profiles")
      .then((res) => setProfiles(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  useEffect(() => {
    const q: Record<string, string> = { date_from: dateFrom, date_to: dateTo };
    if (profileId) q["profile_id"] = profileId;
    api
      .get("/api/v1/reports/tax-liability", { params: q })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [dateFrom, dateTo, profileId]);

  async function downloadCsv() {
    const q: Record<string, string> = {
      date_from: dateFrom,
      date_to: dateTo,
      format: "csv",
    };
    if (profileId) q["profile_id"] = profileId;
    const res = await apiClient.get("/api/v1/reports/tax-liability", {
      params: q,
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `tax-liability-${dateFrom}-to-${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Tax liability report</h1>
        <Button onClick={downloadCsv} data-testid="tl-csv">
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
            data-testid="tl-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="tl-to"
          />
        </label>
        <label className="block text-xs sm:col-span-2">
          Profile
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={profileId}
            onChange={(e) => updateParam("profile_id", e.target.value)}
            data-testid="tl-profile"
          >
            <option value="">All profiles</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} — {p.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[56rem] table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Profile</th>
            <th className="py-2 pr-2">Rate</th>
            <th className="py-2 pr-2">Jurisdiction</th>
            <th className="py-2 pr-2">Rate %</th>
            <th className="py-2 pr-2">Gross taxable</th>
            <th className="py-2 pr-2">Collected</th>
            <th className="py-2 pr-2">Remitted</th>
            <th className="py-2 pr-2">Net</th>
          </tr>
        </thead>
        <tbody>
          {report && report.rows.length ? (
            report.rows.map((row) => (
              <tr key={row.rate_id} className="border-b border-border/50">
                <td className="py-1 pr-2 text-xs">
                  {row.profile_code} · {row.profile_name}
                </td>
                <td className="py-1 pr-2">{row.rate_name}</td>
                <td className="py-1 pr-2 text-xs">{row.jurisdiction}</td>
                <td className="py-1 pr-2">{row.rate}</td>
                <td className="py-1 pr-2">{row.gross_taxable_sales}</td>
                <td className="py-1 pr-2">{row.tax_collected}</td>
                <td className="py-1 pr-2">{row.tax_remitted}</td>
                <td className="py-1 pr-2 font-medium">{row.net_liability}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={8} className="py-4 text-center text-muted-foreground">
                No data for the selected window.
              </td>
            </tr>
          )}
        </tbody>
        {report ? (
          <tfoot>
            <tr className="border-t border-border font-medium">
              <td className="py-2 pr-2" colSpan={5}>
                GRAND TOTAL
              </td>
              <td className="py-2 pr-2">{report.grand_total_collected}</td>
              <td className="py-2 pr-2">{report.grand_total_remitted}</td>
              <td className="py-2 pr-2">{report.grand_total_net}</td>
            </tr>
          </tfoot>
        ) : null}
      </table>
      </div>
    </section>
  );
}
