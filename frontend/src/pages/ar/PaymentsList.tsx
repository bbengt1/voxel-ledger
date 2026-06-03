/**
 * `/payments` — list with state + customer filters.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
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

  const columns: DataTableColumn<PaymentResponse>[] = [
    {
      key: "payment_number",
      header: "Payment #",
      isPrimary: true,
      cell: (p) => (
        <Link to={`/payments/${p.id}`} className="font-mono text-xs hover:underline">
          {p.payment_number}
        </Link>
      ),
    },
    {
      key: "received",
      header: "Received",
      cell: (p) => new Date(p.received_at).toLocaleDateString(),
    },
    { key: "method", header: "Method", cell: (p) => p.method },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      cell: (p) => <span className="font-mono">${p.amount}</span>,
    },
    { key: "state", header: "State", cell: (p) => p.state },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Payments"
        actions={
          canCreate ? (
            <Button asChild>
              <Link to="/payments/new">Record payment</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={4}>
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
      </FilterBar>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(p) => p.id}
        loading={loading && items.length === 0}
        emptyMessage="No payments match these filters."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
