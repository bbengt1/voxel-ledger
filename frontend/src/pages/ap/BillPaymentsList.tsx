/**
 * `/bill-payments` — list with vendor / state / date-range filters.
 * URL-state-backed. Mirrors PaymentsList.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type BillPaymentResponse = components["schemas"]["BillPaymentResponse"];

const STATES = ["pending", "posted", "bounced", "cancelled"] as const;
const CAN_CREATE: readonly string[] = ["owner", "bookkeeper"];

export function BillPaymentsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const vendorId = params.get("vendor_id") ?? "";
  const dateFrom = params.get("date_from") ?? "";
  const dateTo = params.get("date_to") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<BillPaymentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (vendorId) q["vendor_id"] = vendorId;
    if (dateFrom) q["date_from"] = dateFrom;
    if (dateTo) q["date_to"] = dateTo;
    return q;
  }, [stateFilter, vendorId, dateFrom, dateTo]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/bill-payments", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(
          typeof detail === "string" ? detail : "Failed to load bill payments.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<BillPaymentResponse>[] = [
    {
      key: "payment_number",
      header: "Payment #",
      isPrimary: true,
      cell: (p) => (
        <Link
          to={`/bill-payments/${p.id}`}
          className="font-mono text-xs hover:underline"
        >
          {p.payment_number}
        </Link>
      ),
    },
    {
      key: "occurred",
      header: "Occurred",
      cell: (p) => new Date(p.occurred_at).toLocaleDateString(),
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
        title="Bill payments"
        actions={
          canCreate ? (
            <Button asChild>
              <Link to="/bill-payments/new">Record payment</Link>
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
        <label className="block text-xs">
          Date from
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParam("date_from", e.target.value)}
            data-testid="filter-date-from"
          />
        </label>
        <label className="block text-xs">
          Date to
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="filter-date-to"
          />
        </label>
      </FilterBar>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(p) => p.id}
        loading={loading && items.length === 0}
        emptyMessage="No bill payments match."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
