/**
 * `/reports/ar-aging` — bucketed AR aging table. Each row deep-links to
 * `/invoices?customer_id=X`. CSV export opens
 * `/api/v1/reports/ar-aging?format=csv` in a new tab. Operator can
 * override buckets via comma-separated input (`?buckets=`).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ArAgingReportResponse = components["schemas"]["ArAgingReportResponse"];

export function ArAgingReportPage() {
  const [params, setParams] = useSearchParams();
  const bucketsParam = params.get("buckets") ?? "";
  const [bucketsInput, setBucketsInput] = useState(bucketsParam);

  const [report, setReport] = useState<ArAgingReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (bucketsParam.trim()) q["buckets"] = bucketsParam.trim();
    return q;
  }, [bucketsParam]);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/reports/ar-aging", { params: query });
      setReport(res.data as unknown as ArAgingReportResponse);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Failed to load aging report.",
      );
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  function applyBuckets() {
    const next = new URLSearchParams(params);
    if (bucketsInput.trim()) next.set("buckets", bucketsInput.trim());
    else next.delete("buckets");
    setParams(next, { replace: true });
  }

  function downloadCsv() {
    const qs = new URLSearchParams({ format: "csv" });
    if (bucketsParam.trim()) qs.set("buckets", bucketsParam.trim());
    window.open(
      `/api/v1/reports/ar-aging?${qs.toString()}`,
      "_blank",
      "noopener,noreferrer",
    );
  }

  const bucketLabels = report?.bucket_labels ?? [];

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">AR aging</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={downloadCsv}
            data-testid="ar-aging-csv"
          >
            Export CSV
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-2">
        <label className="block text-xs">
          Buckets (days, comma-separated)
          <Input
            value={bucketsInput}
            onChange={(e) => setBucketsInput(e.target.value)}
            placeholder="30,60,90"
            data-testid="ar-aging-buckets"
          />
        </label>
        <Button
          variant="outline"
          onClick={applyBuckets}
          data-testid="ar-aging-apply-buckets"
        >
          Apply
        </Button>
        {report ? (
          <span className="text-xs text-muted-foreground">
            As of {new Date(report.as_of).toLocaleString()}
          </span>
        ) : null}
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Customer</th>
            {bucketLabels.map((label) => (
              <th key={label} className="py-2 pr-2 text-right">
                {label}
              </th>
            ))}
            <th className="py-2 pr-2 text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {loading && !report ? (
            <tr>
              <td
                colSpan={bucketLabels.length + 2}
                className="py-4 text-center text-muted-foreground"
              >
                Loading…
              </td>
            </tr>
          ) : !report || report.rows.length === 0 ? (
            <tr>
              <td
                colSpan={Math.max(2, bucketLabels.length + 2)}
                className="py-4 text-center text-muted-foreground"
              >
                No outstanding balances.
              </td>
            </tr>
          ) : (
            report.rows.map((row) => (
              <tr
                key={row.customer_id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`ar-aging-row-${row.customer_id}`}
              >
                <td className="py-2 pr-2">
                  <Link
                    to={`/invoices?customer_id=${row.customer_id}`}
                    className="hover:underline"
                    data-testid={`ar-aging-drill-${row.customer_id}`}
                  >
                    {row.display_name}{" "}
                    <span className="text-xs text-muted-foreground">
                      ({row.customer_number})
                    </span>
                  </Link>
                </td>
                {row.buckets.map((b, idx) => (
                  <td
                    key={`${row.customer_id}-${idx}`}
                    className="py-2 pr-2 text-right font-mono"
                  >
                    ${b.amount}
                  </td>
                ))}
                <td className="py-2 pr-2 text-right font-mono font-semibold">
                  ${row.total_outstanding}
                </td>
              </tr>
            ))
          )}
        </tbody>
        {report && report.rows.length > 0 ? (
          <tfoot>
            <tr className="border-t border-border text-sm font-semibold">
              <td className="py-2 pr-2">Grand total</td>
              {report.grand_total_by_bucket.map((amt, idx) => (
                <td
                  key={`grand-${idx}`}
                  className="py-2 pr-2 text-right font-mono"
                >
                  ${amt}
                </td>
              ))}
              <td
                className="py-2 pr-2 text-right font-mono"
                data-testid="ar-aging-grand-total"
              >
                ${report.grand_total}
              </td>
            </tr>
          </tfoot>
        ) : null}
      </table>
    </section>
  );
}
