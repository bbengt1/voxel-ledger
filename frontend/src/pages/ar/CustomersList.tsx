/**
 * `/customers` — list with search + active/archived filter. URL-state-
 * backed, mirroring the SalesList pattern.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { BatchOpsDialog } from "@/components/batch/BatchOpsDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type CustomerResponse = components["schemas"]["CustomerResponse"];

const CAN_WRITE: readonly string[] = ["owner", "sales", "bookkeeper"];

export function CustomersListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const state = params.get("state") ?? "active";
  const search = params.get("search") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<CustomerResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [batchOpen, setBatchOpen] = useState(false);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (state) q["state"] = state;
    if (search) q["search"] = search;
    return q;
  }, [state, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/customers", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(
          typeof detail === "string" ? detail : "Failed to load customers.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<CustomerResponse>[] = [
    ...(canWrite
      ? [
          {
            key: "select",
            header: "",
            cell: (c: CustomerResponse) => (
              <input
                type="checkbox"
                data-testid={`customer-select-${c.id}`}
                checked={selected.has(c.id)}
                onChange={() => toggle(c.id)}
              />
            ),
          } as DataTableColumn<CustomerResponse>,
        ]
      : []),
    {
      key: "number",
      header: "#",
      cell: (c) => (
        <Link
          to={`/customers/${c.id}`}
          className="font-mono text-xs hover:underline"
        >
          {c.customer_number}
        </Link>
      ),
    },
    {
      key: "name",
      header: "Name",
      isPrimary: true,
      cell: (c) => c.display_name,
    },
    { key: "email", header: "Email", cell: (c) => c.primary_email ?? "—" },
    { key: "phone", header: "Phone", cell: (c) => c.phone ?? "—" },
    { key: "state", header: "State", cell: (c) => c.state },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Customers"
        actions={
          <>
            {canWrite && selected.size > 0 ? (
              <Button
                type="button"
                variant="outline"
                data-testid="customers-batch-archive"
                onClick={() => setBatchOpen(true)}
              >
                Archive {selected.size} selected
              </Button>
            ) : null}
            {canWrite ? (
              <Button asChild>
                <Link to="/customers/new">New customer</Link>
              </Button>
            ) : null}
          </>
        }
      />

      <FilterBar columns={2}>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={state}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <label className="block text-xs">
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="filter-search"
            placeholder="name / number"
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
        getRowKey={(c) => c.id}
        loading={loading && items.length === 0}
        emptyMessage="No customers match these filters."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />

      <BatchOpsDialog
        open={batchOpen}
        onOpenChange={setBatchOpen}
        entity="customer"
        action="archive"
        ids={Array.from(selected)}
        title={`Archive ${selected.size} customer${selected.size === 1 ? "" : "s"}`}
        onCommitted={() => {
          setSelected(new Set());
          setBatchOpen(false);
          // Re-fetch by toggling a state param so the existing effect re-runs.
          updateParam("state", state);
        }}
      />
    </section>
  );
}
