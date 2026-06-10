import { useCallback, useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type Stats = components["schemas"]["OutboxStatsResponse"];
type Row = components["schemas"]["OutboxRowResponse"];

const STATUS_FILTERS = ["all", "pending", "synced", "failed", "dead"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  synced: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  dead: "bg-zinc-200 text-zinc-800",
};

function fmt(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function detailOf(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
}

/**
 * Admin observability + recovery for the QBO sync outbox (#316 Phase 3e).
 * Shows status counts, a filtered list of outbox rows, and lets an operator
 * requeue failed/dead rows (single or bulk) for the next worker pass.
 */
export function SyncOutboxMonitor() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (status: StatusFilter) => {
    setLoading(true);
    setError(null);
    try {
      const statsRes = await api.get("/api/v1/admin/quickbooks/outbox/stats");
      setStats(statsRes.data);
      const listRes = await api.get("/api/v1/admin/quickbooks/outbox", {
        params: status === "all" ? { limit: 50 } : { status, limit: 50 },
      });
      setRows(listRes.data.items);
    } catch {
      setError("Failed to load the sync outbox.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filter);
  }, [load, filter]);

  async function retryRow(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/admin/quickbooks/outbox/${id}/retry`, null);
      await load(filter);
    } catch (err: unknown) {
      setError(detailOf(err) ?? "Failed to retry that row.");
    } finally {
      setBusy(false);
    }
  }

  async function retryAll(status: "failed" | "dead") {
    const n = status === "failed" ? stats?.failed : stats?.dead;
    if (!n) return;
    if (!window.confirm(`Requeue all ${n} ${status} row(s) for the next sync pass?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/v1/admin/quickbooks/outbox/retry", { status });
      await load(filter);
    } catch (err: unknown) {
      setError(detailOf(err) ?? `Failed to retry ${status} rows.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 border-t pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Sync outbox</h3>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => retryAll("failed")}
            disabled={busy || !stats?.failed}
          >
            Retry all failed{stats?.failed ? ` (${stats.failed})` : ""}
          </Button>
          <Button
            variant="outline"
            onClick={() => retryAll("dead")}
            disabled={busy || !stats?.dead}
          >
            Retry all dead{stats?.dead ? ` (${stats.dead})` : ""}
          </Button>
          <Button variant="outline" onClick={() => load(filter)} disabled={busy || loading}>
            Refresh
          </Button>
        </div>
      </div>

      {stats ? (
        <div className="flex flex-wrap gap-2 text-xs">
          <StatChip label="Pending" value={stats.pending} tone="bg-amber-100 text-amber-800" />
          <StatChip label="Synced" value={stats.synced} tone="bg-green-100 text-green-800" />
          <StatChip label="Failed" value={stats.failed} tone="bg-red-100 text-red-800" />
          <StatChip label="Dead" value={stats.dead} tone="bg-zinc-200 text-zinc-800" />
          <StatChip label="Total" value={stats.total} tone="bg-muted text-foreground" />
        </div>
      ) : null}

      <div className="flex gap-1">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setFilter(s)}
            className={`rounded px-2 py-1 text-xs capitalize ${
              filter === s ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-2 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No outbox rows.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="py-1 pr-3">Kind</th>
                <th className="py-1 pr-3">Op</th>
                <th className="py-1 pr-3">Status</th>
                <th className="py-1 pr-3">Attempts</th>
                <th className="py-1 pr-3">QBO ID</th>
                <th className="py-1 pr-3">Last error</th>
                <th className="py-1 pr-3">Created</th>
                <th className="py-1" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const retryable = r.status === "failed" || r.status === "dead";
                return (
                  <tr key={r.id} className="border-b align-top">
                    <td className="py-1 pr-3 font-medium">{r.kind}</td>
                    <td className="py-1 pr-3">{r.op}</td>
                    <td className="py-1 pr-3">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs ${
                          STATUS_STYLE[r.status] ?? "bg-muted"
                        }`}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="py-1 pr-3">{r.attempts}</td>
                    <td className="py-1 pr-3">{r.qbo_id ?? "—"}</td>
                    <td className="max-w-xs py-1 pr-3 text-xs text-muted-foreground">
                      {r.last_error ? (
                        <span className="line-clamp-2" title={r.last_error}>
                          {r.last_error}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-1 pr-3 whitespace-nowrap text-xs">{fmt(r.created_at)}</td>
                    <td className="py-1">
                      {retryable ? (
                        <Button
                          variant="outline"
                          className="h-7 px-2 text-xs"
                          onClick={() => retryRow(r.id)}
                          disabled={busy}
                        >
                          Retry
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatChip({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <span className={`rounded px-2 py-1 font-medium ${tone}`}>
      {label}: {value}
    </span>
  );
}
