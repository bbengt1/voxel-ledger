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
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
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

  const columns: DataTableColumn<RefundResponse>[] = [
    {
      key: "refund_number",
      header: "Refund #",
      isPrimary: true,
      cell: (r) => (
        <Link
          to={`/sales/refunds/${r.id}`}
          className="font-mono text-xs hover:underline"
        >
          {r.refund_number}
        </Link>
      ),
    },
    { key: "state", header: "State", cell: (r) => r.state.replace(/_/g, " ") },
    { key: "kind", header: "Kind", cell: (r) => r.kind.replace(/_/g, " ") },
    {
      key: "total",
      header: "Total",
      align: "right",
      cell: (r) => <span className="tabular-nums">{r.total_amount}</span>,
    },
    {
      key: "reason",
      header: "Reason",
      cell: (r) => (
        <span className="truncate" title={r.reason_code}>
          {r.reason_code}
        </span>
      ),
    },
    {
      key: "created",
      header: "Created",
      cell: (r) => new Date(r.created_at).toLocaleDateString(),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Refunds"
        description="New refunds are started from a sale's detail page."
      />

      <FilterBar columns={2}>
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
      </FilterBar>

      {error ? (
        <div
          role="alert"
          data-testid="refunds-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(r) => r.id}
        loading={loading && items.length === 0}
        emptyMessage="No refunds match these filters."
        minWidthClassName="min-w-[680px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
