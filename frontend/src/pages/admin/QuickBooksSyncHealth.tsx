import { useCallback, useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type Reconciliation = components["schemas"]["ReconciliationResponse"];
type DriftRow = components["schemas"]["DriftRowResponse"];

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function fmt(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function detailOf(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
}

/**
 * Sync-health + decommission-ready surface (#317 Phase 4c). Shows the QBO
 * completeness report (gaps, drift, outbox backlog) over a date range and the
 * single go/no-go signal Phase 5 checks, plus an acknowledge action for drift.
 */
export function SyncHealthPanel() {
  const [from, setFrom] = useState(() => isoDaysAgo(90));
  const [to, setTo] = useState(() => today());
  const [report, setReport] = useState<Reconciliation | null>(null);
  const [drift, setDrift] = useState<DriftRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (f: string, t: string) => {
    setLoading(true);
    setError(null);
    try {
      const rec = await api.get("/api/v1/admin/quickbooks/reconciliation", {
        params: { from: f, to: t },
      });
      setReport(rec.data);
      const d = await api.get("/api/v1/admin/quickbooks/drift", {
        params: { status: "open", limit: 100 },
      });
      setDrift(d.data.items);
    } catch (err: unknown) {
      setError(detailOf(err) ?? "Failed to load sync health.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(from, to);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function acknowledge(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/admin/quickbooks/drift/${id}/acknowledge`, null);
      await load(from, to);
    } catch (err: unknown) {
      setError(detailOf(err) ?? "Failed to acknowledge drift.");
    } finally {
      setBusy(false);
    }
  }

  const ready = report?.decommission_ready === true;

  return (
    <div className="flex flex-col gap-3 border-t pt-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h3 className="text-sm font-semibold">Sync health &amp; decommission readiness</h3>
        <div className="flex items-end gap-2">
          <label className="flex flex-col text-xs text-muted-foreground">
            From
            <input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="rounded border px-2 py-1 text-sm text-foreground"
            />
          </label>
          <label className="flex flex-col text-xs text-muted-foreground">
            To
            <input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="rounded border px-2 py-1 text-sm text-foreground"
            />
          </label>
          <Button variant="outline" onClick={() => load(from, to)} disabled={busy || loading}>
            Run
          </Button>
        </div>
      </div>

      {report ? (
        <div
          className={`rounded border p-3 text-sm ${
            ready
              ? "border-green-600 bg-green-50 text-green-800"
              : "border-amber-600 bg-amber-50 text-amber-800"
          }`}
        >
          <span className="font-semibold">
            {ready ? "✓ Decommission-ready" : "✗ Not decommission-ready"}
          </span>
          <span className="block text-xs">
            {ready
              ? "Outbox drained, no gaps in range, no open drift. Safe for Phase 5 GL removal."
              : "Resolve the items below before removing the local GL (Phase 5)."}
          </span>
        </div>
      ) : null}

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-2 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      {report ? (
        <div className="flex flex-wrap gap-2 text-xs">
          <Chip label="Gaps" value={report.gap_count} bad={report.gap_count > 0} />
          <Chip label="Open drift" value={report.drift_open} bad={report.drift_open > 0} />
          <Chip
            label="Mismatch candidates"
            value={report.mismatch_candidates}
            bad={report.mismatch_candidates > 0}
          />
          <Chip
            label="Outbox pending"
            value={report.outbox.pending ?? 0}
            bad={(report.outbox.pending ?? 0) > 0}
          />
          <Chip
            label="Outbox failed"
            value={report.outbox.failed ?? 0}
            bad={(report.outbox.failed ?? 0) > 0}
          />
          <Chip
            label="Outbox dead"
            value={report.outbox.dead ?? 0}
            bad={(report.outbox.dead ?? 0) > 0}
          />
        </div>
      ) : null}

      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}

      {report && report.gaps.length > 0 ? (
        <div className="flex flex-col gap-1">
          <h4 className="text-xs font-semibold text-muted-foreground">
            Gaps — finalized records with no synced QBO document
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-1 pr-3">Kind</th>
                  <th className="py-1 pr-3">Reference</th>
                  <th className="py-1 pr-3">When</th>
                </tr>
              </thead>
              <tbody>
                {report.gaps.map((g) => (
                  <tr key={`${g.kind}-${g.local_id}`} className="border-b">
                    <td className="py-1 pr-3 font-medium">{g.kind}</td>
                    <td className="py-1 pr-3">{g.reference ?? g.local_id}</td>
                    <td className="py-1 pr-3 whitespace-nowrap text-xs">{fmt(g.occurred_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {drift.length > 0 ? (
        <div className="flex flex-col gap-1">
          <h4 className="text-xs font-semibold text-muted-foreground">
            Open drift — entities edited/deleted directly in QuickBooks
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-1 pr-3">Entity</th>
                  <th className="py-1 pr-3">QBO ID</th>
                  <th className="py-1 pr-3">Change</th>
                  <th className="py-1 pr-3">Local kind</th>
                  <th className="py-1 pr-3">Seen</th>
                  <th className="py-1 pr-3">Last detected</th>
                  <th className="py-1" />
                </tr>
              </thead>
              <tbody>
                {drift.map((d) => (
                  <tr key={d.id} className="border-b">
                    <td className="py-1 pr-3 font-medium">{d.entity_type}</td>
                    <td className="py-1 pr-3">{d.qbo_id}</td>
                    <td className="py-1 pr-3">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs ${
                          d.change_type === "deleted"
                            ? "bg-red-100 text-red-800"
                            : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {d.change_type}
                      </span>
                    </td>
                    <td className="py-1 pr-3">{d.local_kind ?? "—"}</td>
                    <td className="py-1 pr-3">{d.occurrences}×</td>
                    <td className="py-1 pr-3 whitespace-nowrap text-xs">
                      {fmt(d.last_detected_at)}
                    </td>
                    <td className="py-1">
                      <Button
                        variant="outline"
                        className="h-7 px-2 text-xs"
                        onClick={() => acknowledge(d.id)}
                        disabled={busy}
                      >
                        Acknowledge
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Chip({ label, value, bad }: { label: string; value: number; bad: boolean }) {
  return (
    <span
      className={`rounded px-2 py-1 font-medium ${
        bad ? "bg-red-100 text-red-800" : "bg-green-100 text-green-800"
      }`}
    >
      {label}: {value}
    </span>
  );
}
