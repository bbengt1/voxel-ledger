/**
 * `/sales` — sales list with URL-state-backed filters (state, channel,
 * date range, search).
 *
 * Phase 6.7a. Matches the JobsList pattern from Phase 5.6a.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type SaleResponse = components["schemas"]["SaleResponse"];
type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];

const STATES = ["draft", "confirmed", "fulfilled", "cancelled"] as const;
const CAN_CREATE: readonly string[] = ["owner", "sales", "bookkeeper"];

export function SalesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const channelId = params.get("channel_id") ?? "";
  const search = params.get("search") ?? "";
  const dateFrom = params.get("date_from") ?? "";
  const dateTo = params.get("date_to") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<SaleResponse[]>([]);
  const [channels, setChannels] = useState<SalesChannelResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (channelId) q["channel_id"] = channelId;
    if (search) q["search"] = search;
    if (dateFrom) q["date_from"] = dateFrom;
    if (dateTo) q["date_to"] = dateTo;
    return q;
  }, [stateFilter, channelId, search, dateFrom, dateTo]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/sales", { params: query })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load sales.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  useEffect(() => {
    api
      .get("/api/v1/sales-channels")
      .then((res) => setChannels(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  const channelName = (id: string) =>
    channels.find((c) => c.id === id)?.name ?? id.slice(0, 8);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Sales</h1>
        <div className="flex gap-2">
          {canCreate ? (
            <Button asChild>
              <Link to="/sales/new">New sale</Link>
            </Button>
          ) : null}
        </div>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={stateFilter}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="">All</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
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
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="filter-search"
            placeholder="customer / sale#"
          />
        </label>
        <label className="block text-xs">
          From
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParam("date_from", e.target.value)}
            data-testid="filter-date-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="filter-date-to"
          />
        </label>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="sales-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Sale #</th>
            <th className="py-2 pr-2">Occurred</th>
            <th className="py-2 pr-2">Channel</th>
            <th className="py-2 pr-2">Customer</th>
            <th className="py-2 pr-2 text-right">Total</th>
            <th className="py-2 pr-2">State</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No sales match these filters.
              </td>
            </tr>
          ) : (
            items.map((s) => (
              <tr
                key={s.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`sale-row-${s.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link
                    to={`/sales/${s.id}`}
                    className="hover:underline"
                  >
                    {s.sale_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">
                  {new Date(s.occurred_at).toLocaleDateString()}
                </td>
                <td className="py-2 pr-2">{channelName(s.channel_id)}</td>
                <td className="py-2 pr-2">{s.customer_name}</td>
                <td className="py-2 pr-2 text-right font-mono">
                  ${s.total_amount}
                </td>
                <td className="py-2 pr-2">{s.state}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
