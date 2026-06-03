/**
 * `/vendors` — list with search + active/archived filter. URL-state-
 * backed, mirroring CustomersList.
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

type VendorResponse = components["schemas"]["VendorResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function VendorsListPage() {
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

  const [items, setItems] = useState<VendorResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      .get("/api/v1/vendors", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load vendors.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<VendorResponse>[] = [
    {
      key: "vendor_number",
      header: "#",
      isPrimary: true,
      cell: (v) => (
        <Link
          to={`/vendors/${v.id}`}
          className="font-mono text-xs hover:underline"
        >
          {v.vendor_number}
        </Link>
      ),
    },
    { key: "name", header: "Name", cell: (v) => v.display_name },
    { key: "email", header: "Email", cell: (v) => v.primary_email ?? "—" },
    { key: "terms", header: "Terms", cell: (v) => `${v.payment_terms_days}d` },
    { key: "state", header: "State", cell: (v) => v.state },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Vendors"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/vendors/new">New vendor</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={3}>
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
        getRowKey={(v) => v.id}
        loading={loading && items.length === 0}
        emptyMessage="No vendors match these filters."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
