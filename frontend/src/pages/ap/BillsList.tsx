/**
 * `/bills` — list with state / vendor / due-range / overdue / search
 * filters. URL-state-backed. Mirrors InvoicesList.
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

type BillResponse = components["schemas"]["BillResponse"];

const STATES = [
  "draft",
  "issued",
  "partially_paid",
  "paid",
  "overdue",
  "void",
] as const;
const CAN_CREATE: readonly string[] = ["owner", "bookkeeper"];

export function BillsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const vendorId = params.get("vendor_id") ?? "";
  const dueFrom = params.get("due_from") ?? "";
  const dueTo = params.get("due_to") ?? "";
  const overdue = params.get("overdue") === "true";
  const search = params.get("search") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<BillResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (vendorId) q["vendor_id"] = vendorId;
    if (dueFrom) q["due_from"] = dueFrom;
    if (dueTo) q["due_to"] = dueTo;
    if (overdue) q["overdue"] = "true";
    if (search) q["search"] = search;
    return q;
  }, [stateFilter, vendorId, dueFrom, dueTo, overdue, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/bills", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load bills.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<BillResponse>[] = [
    {
      key: "bill_number",
      header: "Bill #",
      isPrimary: true,
      cell: (b) => (
        <Link
          to={`/bills/${b.id}`}
          className="font-mono text-xs hover:underline"
        >
          {b.bill_number}
        </Link>
      ),
    },
    {
      key: "issued",
      header: "Issued",
      cell: (b) =>
        b.issued_at ? new Date(b.issued_at).toLocaleDateString() : "—",
    },
    {
      key: "due",
      header: "Due",
      cell: (b) => (b.due_at ? new Date(b.due_at).toLocaleDateString() : "—"),
    },
    {
      key: "total",
      header: "Total",
      align: "right",
      cell: (b) => <span className="font-mono">${b.total_amount}</span>,
    },
    {
      key: "outstanding",
      header: "Outstanding",
      align: "right",
      cell: (b) => <span className="font-mono">${b.amount_outstanding}</span>,
    },
    { key: "state", header: "State", cell: (b) => b.state },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Bills"
        actions={
          canCreate ? (
            <Button asChild>
              <Link to="/bills/new">New bill</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={5}>
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
        <label className="block text-xs">
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="filter-search"
            placeholder="bill # / vendor inv #"
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
        getRowKey={(b) => b.id}
        loading={loading && items.length === 0}
        emptyMessage="No bills match these filters."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
