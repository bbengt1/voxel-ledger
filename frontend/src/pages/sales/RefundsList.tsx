/**
 * `/sales/refunds` — list of refunds with state + sale-id filters.
 *
 * Thin wrapper over GET /api/v1/refunds. Rows link into the refund
 * detail page at /sales/refunds/{id}. New refunds are still started
 * from a sale's detail page (refund composer), so there's no "New"
 * affordance here.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Input } from "@/components/ui/Input";

type RefundResponse = components["schemas"]["RefundResponse"];

const STATES = [
  "pending_approval",
  "approved",
  "posted",
  "rejected",
  "cancelled",
] as const;

export function RefundsListPage() {
  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const saleId = params.get("sale_id") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<RefundResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (saleId) q["sale_id"] = saleId;
    return q;
  }, [stateFilter, saleId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/refunds", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load refunds.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Refunds</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          New refunds are started from a sale's detail page.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={stateFilter}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="refunds-filter-state"
          >
            <option value="">All</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Sale ID
          <Input
            value={saleId}
            onChange={(e) => updateParam("sale_id", e.target.value)}
            data-testid="refunds-filter-sale"
          />
        </label>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="refunds-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Refund #</th>
            <th className="py-2 pr-2">State</th>
            <th className="py-2 pr-2">Kind</th>
            <th className="py-2 pr-2 text-right">Total</th>
            <th className="py-2 pr-2">Reason</th>
            <th className="py-2 pr-2">Created</th>
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
                No refunds match these filters.
              </td>
            </tr>
          ) : (
            items.map((r) => (
              <tr
                key={r.id}
                className="border-b border-border/50 hover:bg-accent/30"
              >
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link
                    to={`/sales/refunds/${r.id}`}
                    className="hover:underline"
                  >
                    {r.refund_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">{r.state.replace(/_/g, " ")}</td>
                <td className="py-2 pr-2">{r.kind.replace(/_/g, " ")}</td>
                <td className="py-2 pr-2 text-right tabular-nums">
                  {r.total_amount}
                </td>
                <td className="py-2 pr-2 truncate" title={r.reason_code}>
                  {r.reason_code}
                </td>
                <td className="py-2 pr-2">
                  {new Date(r.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
