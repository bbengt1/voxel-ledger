/**
 * `/invoices` — list with state / customer / due-range / overdue filters,
 * URL-state-backed.
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

type InvoiceResponse = components["schemas"]["InvoiceResponse"];

const STATES = [
  "draft",
  "issued",
  "partially_paid",
  "paid",
  "overdue",
  "void",
] as const;
const CAN_CREATE: readonly string[] = ["owner", "sales", "bookkeeper"];

export function InvoicesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const customerId = params.get("customer_id") ?? "";
  const dueFrom = params.get("due_from") ?? "";
  const dueTo = params.get("due_to") ?? "";
  const overdue = params.get("overdue") === "true";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<InvoiceResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (customerId) q["customer_id"] = customerId;
    if (dueFrom) q["due_from"] = dueFrom;
    if (dueTo) q["due_to"] = dueTo;
    if (overdue) q["overdue"] = "true";
    return q;
  }, [stateFilter, customerId, dueFrom, dueTo, overdue]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/invoices", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load invoices.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<InvoiceResponse>[] = [
    {
      key: "invoice_number",
      header: "Invoice #",
      isPrimary: true,
      cell: (i) => (
        <Link to={`/invoices/${i.id}`} className="font-mono text-xs hover:underline">
          {i.invoice_number}
        </Link>
      ),
    },
    {
      key: "issued",
      header: "Issued",
      cell: (i) => (i.issued_at ? new Date(i.issued_at).toLocaleDateString() : "—"),
    },
    {
      key: "due",
      header: "Due",
      cell: (i) => (i.due_at ? new Date(i.due_at).toLocaleDateString() : "—"),
    },
    {
      key: "total",
      header: "Total",
      align: "right",
      cell: (i) => <span className="font-mono">${i.total_amount}</span>,
    },
    {
      key: "outstanding",
      header: "Outstanding",
      align: "right",
      cell: (i) => <span className="font-mono">${i.amount_outstanding}</span>,
    },
    { key: "state", header: "State", cell: (i) => i.state },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Invoices"
        actions={
          canCreate ? (
            <Button asChild>
              <Link to="/invoices/new">New invoice</Link>
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
          Due from
          <Input
            type="date"
            value={dueFrom}
            onChange={(e) => updateParam("due_from", e.target.value)}
            data-testid="filter-due-from"
          />
        </label>
        <label className="block text-xs">
          Due to
          <Input
            type="date"
            value={dueTo}
            onChange={(e) => updateParam("due_to", e.target.value)}
            data-testid="filter-due-to"
          />
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={overdue}
            onChange={(e) => updateParam("overdue", e.target.checked ? "true" : "")}
            data-testid="filter-overdue"
          />
          Overdue only
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
        getRowKey={(i) => i.id}
        loading={loading && items.length === 0}
        emptyMessage="No invoices match these filters."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
