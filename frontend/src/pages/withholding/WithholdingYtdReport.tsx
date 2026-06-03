/**
 * `/reports/withholding-1099` — year-end withholding report
 * (Phase 9.10b, #162). One row per vendor: paid + withheld YTD.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type ReportResponse = components["schemas"]["WithholdingYtdReportResponse"];

function thisYear() {
  return String(new Date().getFullYear());
}

export function WithholdingYtdReportPage() {
  const [params, setParams] = useSearchParams();
  const year = params.get("year") ?? thisYear();

  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateYear(value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set("year", value);
    else next.delete("year");
    setParams(next, { replace: true });
  }

  useEffect(() => {
    api
      .get("/api/v1/withholding/ytd-by-vendor", { params: { year } })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [year]);

  async function downloadCsv() {
    const res = await apiClient.get("/api/v1/withholding/ytd-by-vendor", {
      params: { year, format: "csv" },
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `withholding-ytd-${year}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Withholding YTD (1099)</h1>
        <Button onClick={downloadCsv} data-testid="wy-csv">
          Download CSV
        </Button>
      </header>

      <label className="block text-xs sm:w-32">
        Year
        <input
          type="number"
          min={2000}
          max={2999}
          className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          value={year}
          onChange={(e) => updateYear(e.target.value)}
          data-testid="wy-year"
        />
      </label>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[44rem] table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Vendor #</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Profile</th>
            <th className="py-2 pr-2">Form</th>
            <th className="py-2 pr-2">Total paid</th>
            <th className="py-2 pr-2">Total withheld</th>
          </tr>
        </thead>
        <tbody>
          {report && report.rows.length ? (
            report.rows.map((row) => (
              <tr key={row.vendor_id} className="border-b border-border/50">
                <td className="py-1 pr-2 font-mono text-xs">{row.vendor_number}</td>
                <td className="py-1 pr-2">{row.display_name}</td>
                <td className="py-1 pr-2 text-xs">{row.profile_code ?? "—"}</td>
                <td className="py-1 pr-2 text-xs">{row.form_kind ?? "—"}</td>
                <td className="py-1 pr-2">{row.total_paid}</td>
                <td className="py-1 pr-2">{row.total_withheld}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No withholding activity in {year}.
              </td>
            </tr>
          )}
        </tbody>
        {report ? (
          <tfoot>
            <tr className="border-t border-border font-medium">
              <td className="py-2 pr-2" colSpan={4}>
                GRAND TOTAL
              </td>
              <td className="py-2 pr-2">{report.grand_total_paid}</td>
              <td className="py-2 pr-2">{report.grand_total_withheld}</td>
            </tr>
          </tfoot>
        ) : null}
      </table>
      </div>
    </section>
  );
}
