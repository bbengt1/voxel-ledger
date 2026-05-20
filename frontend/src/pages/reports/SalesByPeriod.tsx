/**
 * `/reports/sales-by-period` — gross / refunds / net / order count per
 * (channel, bucket) (Phase 10.8b, #183). Bucket selector for day /
 * week / month / quarter / year. CSV export.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["SalesByPeriodResponse"];
type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];

function defaultRange() {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth() - 5, 1);
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: today.toISOString().slice(0, 10),
  };
}

export function SalesByPeriodPage() {
  const [params, setParams] = useSearchParams();
  const defaults = defaultRange();
  const dateFrom = params.get("date_from") ?? defaults.date_from;
  const dateTo = params.get("date_to") ?? defaults.date_to;
  const bucket = params.get("bucket") ?? "month";
  const channelId = params.get("channel_id") ?? "";

  const [channels, setChannels] = useState<SalesChannelResponse[]>([]);
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
      .get("/api/v1/sales-channels")
      .then((res) => setChannels(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  useEffect(() => {
    const q: Record<string, string> = {
      date_from: dateFrom,
      date_to: dateTo,
      bucket,
    };
    if (channelId) q["channel_id"] = channelId;
    api
      .get("/api/v1/reports/sales-by-period", { params: q })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [dateFrom, dateTo, bucket, channelId]);

  async function downloadCsv() {
    const q: Record<string, string> = {
      date_from: dateFrom,
      date_to: dateTo,
      bucket,
      format: "csv",
    };
    if (channelId) q["channel_id"] = channelId;
    const res = await apiClient.get("/api/v1/reports/sales-by-period", {
      params: q,
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `sales-by-period-${dateFrom}-to-${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const channelName = (id: string) =>
    channels.find((c) => c.id === id)?.name ?? id.slice(0, 8);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Sales by period</h1>
        <Button onClick={downloadCsv} data-testid="sbp-csv">
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
            data-testid="sbp-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="sbp-to"
          />
        </label>
        <label className="block text-xs">
          Bucket
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={bucket}
            onChange={(e) => updateParam("bucket", e.target.value)}
            data-testid="sbp-bucket"
          >
            <option value="day">Day</option>
            <option value="week">Week</option>
            <option value="month">Month</option>
            <option value="quarter">Quarter</option>
            <option value="year">Year</option>
          </select>
        </label>
        <label className="block text-xs">
          Channel
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={channelId}
            onChange={(e) => updateParam("channel_id", e.target.value)}
            data-testid="sbp-channel"
          >
            <option value="">All channels</option>
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
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

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Bucket</th>
            <th className="py-2 pr-2">Channel</th>
            <th className="py-2 pr-2 text-right">Gross</th>
            <th className="py-2 pr-2 text-right">Refunds</th>
            <th className="py-2 pr-2 text-right">Net</th>
            <th className="py-2 pr-2 text-right">Orders</th>
          </tr>
        </thead>
        <tbody>
          {report && report.rows.length ? (
            report.rows.map((r, i) => (
              <tr key={i} className="border-b border-border/30">
                <td className="py-1 pr-2">{r.bucket_start}</td>
                <td className="py-1 pr-2 text-xs">{channelName(r.channel_id)}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{r.gross_sales}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{r.refunds}</td>
                <td className="py-1 pr-2 text-right tabular-nums font-medium">{r.net_sales}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{r.order_count}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No sales in this window.
              </td>
            </tr>
          )}
        </tbody>
        {report ? (
          <tfoot>
            <tr className="border-t-2 border-primary font-semibold">
              <td colSpan={2} className="py-2 pr-2">GRAND TOTAL</td>
              <td className="py-2 pr-2 text-right tabular-nums">{report.total_gross}</td>
              <td className="py-2 pr-2 text-right tabular-nums">{report.total_refunds}</td>
              <td className="py-2 pr-2 text-right tabular-nums">{report.total_net}</td>
              <td className="py-2 pr-2 text-right tabular-nums">{report.total_orders}</td>
            </tr>
          </tfoot>
        ) : null}
      </table>
    </section>
  );
}
