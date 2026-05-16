/**
 * `/payments` — list with state + customer filters.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type PaymentResponse = components["schemas"]["PaymentResponse"];

const STATES = ["pending", "applied", "cancelled", "bounced"] as const;
const CAN_CREATE: readonly string[] = ["owner", "sales", "bookkeeper"];

export function PaymentsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const customerId = params.get("customer_id") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<PaymentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (customerId) q["customer_id"] = customerId;
    return q;
  }, [stateFilter, customerId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/payments", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load payments.");
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
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Payments</h1>
        {canCreate ? (
          <Button asChild>
            <Link to="/payments/new">Record payment</Link>
          </Button>
        ) : null}
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
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
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Payment #</th>
            <th className="py-2 pr-2">Received</th>
            <th className="py-2 pr-2">Method</th>
            <th className="py-2 pr-2 text-right">Amount</th>
            <th className="py-2 pr-2">State</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                No payments match these filters.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr
                key={p.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`payment-row-${p.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link to={`/payments/${p.id}`} className="hover:underline">
                    {p.payment_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">
                  {new Date(p.received_at).toLocaleDateString()}
                </td>
                <td className="py-2 pr-2">{p.method}</td>
                <td className="py-2 pr-2 text-right font-mono">${p.amount}</td>
                <td className="py-2 pr-2">{p.state}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
