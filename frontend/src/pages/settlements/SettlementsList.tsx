/**
 * `/settlements` — settlement list with channel + state filters
 * (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type SettlementResponse = components["schemas"]["SettlementResponse"];
type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function SettlementsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const state = params.get("state") ?? "";
  const channelId = params.get("channel_id") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<SettlementResponse[]>([]);
  const [channels, setChannels] = useState<SalesChannelResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/sales-channels")
      .then((res) => setChannels(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  useEffect(() => {
    const q: Record<string, string> = {};
    if (state) q["state"] = state;
    if (channelId) q["channel_id"] = channelId;
    api
      .get("/api/v1/settlements", { params: q })
      .then((res) => setItems(res.data.items))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load settlements.");
      });
  }, [state, channelId]);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Settlements</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/settlements/import">Import settlement</Link>
          </Button>
        ) : null}
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label className="block text-xs">
          Channel
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={channelId}
            onChange={(e) => updateParam("channel_id", e.target.value)}
            data-testid="filter-channel"
          >
            <option value="">All</option>
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={state}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="">All</option>
            <option value="imported">Imported</option>
            <option value="matched">Matched</option>
            <option value="posted">Posted</option>
            <option value="cancelled">Cancelled</option>
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
            <th className="py-2 pr-2">#</th>
            <th className="py-2 pr-2">Period</th>
            <th className="py-2 pr-2">Gross</th>
            <th className="py-2 pr-2">Fees</th>
            <th className="py-2 pr-2">Payout</th>
            <th className="py-2 pr-2">State</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No settlements yet.
              </td>
            </tr>
          ) : (
            items.map((s) => (
              <tr key={s.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link to={`/settlements/${s.id}`} className="hover:underline">
                    {s.settlement_number}
                  </Link>
                </td>
                <td className="py-2 pr-2 text-xs">
                  {s.period_start} → {s.period_end}
                </td>
                <td className="py-2 pr-2">{s.gross_amount}</td>
                <td className="py-2 pr-2">{s.fee_amount}</td>
                <td className="py-2 pr-2">{s.payout_amount}</td>
                <td className="py-2 pr-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {s.state}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
