/**
 * `/control-center` — Admin aggregate dashboard (Phase 11.5, #197).
 * Backed by `GET /api/v1/control-center` (Phase 11.4, #196).
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";

type CCResponse = components["schemas"]["ControlCenterResponse"];

function Card({
  title,
  count,
  amount,
  sample,
  testId,
}: {
  title: string;
  count: number;
  amount?: string;
  sample: Record<string, unknown>[];
  testId: string;
}) {
  return (
    <div
      data-testid={testId}
      className="rounded border border-border bg-background p-4 shadow-sm"
    >
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-medium uppercase text-muted-foreground">
          {title}
        </div>
        <div className="tabular-nums text-2xl font-semibold">{count}</div>
      </div>
      {amount ? (
        <div className="pt-1 text-xs text-muted-foreground tabular-nums">
          Total: {amount}
        </div>
      ) : null}
      <ul className="pt-2 space-y-1 text-xs text-muted-foreground">
        {count === 0 ? (
          <li className="italic">Nothing to see — you're caught up.</li>
        ) : (
          sample.slice(0, 5).map((row, i) => (
            <li key={String(row.id ?? i)} className="font-mono truncate">
              {Object.entries(row)
                .filter(([k]) => k !== "id")
                .map(([, v]) => String(v))
                .join(" · ")}
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

export function ControlCenterPage() {
  const [data, setData] = useState<CCResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const resp = await api.get("/api/v1/control-center");
        if (!cancelled) setData(resp.data as CCResponse);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Load failed");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="p-6 text-red-600">{error}</div>;
  if (!data) return <div className="p-6 text-muted-foreground">Loading...</div>;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Control Center</h1>
        <div className="text-xs text-muted-foreground">
          as of {new Date(data.as_of).toLocaleString()}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Card
          title="Pending approvals"
          count={data.pending_approvals.count}
          sample={data.pending_approvals.sample as Record<string, unknown>[]}
          testId="cc-pending-approvals"
        />
        <Card
          title="Low stock"
          count={data.low_stock_alerts.count}
          sample={data.low_stock_alerts.sample as Record<string, unknown>[]}
          testId="cc-low-stock"
        />
        <Card
          title="Overdue invoices"
          count={data.overdue_invoices.count}
          amount={String(data.overdue_invoices.amount_total)}
          sample={data.overdue_invoices.sample as Record<string, unknown>[]}
          testId="cc-overdue-invoices"
        />
        <Card
          title="Overdue bills"
          count={data.overdue_bills.count}
          amount={String(data.overdue_bills.amount_total)}
          sample={data.overdue_bills.sample as Record<string, unknown>[]}
          testId="cc-overdue-bills"
        />
        <Card
          title="Webhook DLQ"
          count={data.webhook_dlq.count}
          sample={data.webhook_dlq.sample as Record<string, unknown>[]}
          testId="cc-webhook-dlq"
        />
        <Card
          title="Failed jobs"
          count={data.failed_jobs.count}
          sample={data.failed_jobs.sample as Record<string, unknown>[]}
          testId="cc-failed-jobs"
        />
      </div>
      <div className="rounded border border-border bg-background p-4">
        <div className="text-sm font-medium uppercase text-muted-foreground">
          WebSocket health
        </div>
        <div className="pt-1 text-sm">
          Moonraker WS:{" "}
          <span
            data-testid="cc-ws-status"
            className={
              data.ws_health.moonraker_ws_connected
                ? "text-green-700"
                : "text-amber-700"
            }
          >
            {data.ws_health.moonraker_ws_connected ? "connected" : "not connected"}
          </span>
          {data.ws_health.last_event_at ? (
            <span className="pl-2 text-xs text-muted-foreground">
              last event at {data.ws_health.last_event_at}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
