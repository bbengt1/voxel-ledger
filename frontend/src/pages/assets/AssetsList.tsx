/**
 * `/assets` — fixed-asset register (Phase 9.10a, #162).
 *
 * Filters by kind, asset_class, state, and free-text search. URL-state-
 * backed so deep links round-trip.
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

type AssetResponse = components["schemas"]["FixedAssetResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function AssetsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const assetClass = params.get("asset_class") ?? "";
  const state = params.get("state") ?? "";
  const search = params.get("search") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<AssetResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (kind) q["kind"] = kind;
    if (assetClass) q["asset_class"] = assetClass;
    if (state) q["state"] = state;
    if (search) q["search"] = search;
    return q;
  }, [kind, assetClass, state, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/fixed-assets", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load assets.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<AssetResponse>[] = [
    {
      key: "asset_number",
      header: "#",
      isPrimary: true,
      cell: (a) => (
        <Link
          to={`/assets/${a.id}`}
          className="font-mono text-xs hover:underline"
        >
          {a.asset_number}
        </Link>
      ),
    },
    { key: "name", header: "Name", cell: (a) => a.name },
    {
      key: "class",
      header: "Class",
      cell: (a) => (
        <span className="text-xs">
          {a.kind} · {a.asset_class}
        </span>
      ),
    },
    {
      key: "acquisition_cost",
      header: "Cost",
      align: "right",
      cell: (a) => a.acquisition_cost,
    },
    { key: "acquired_on", header: "Acquired", cell: (a) => a.acquired_on },
    {
      key: "state",
      header: "State",
      cell: (a) => (
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{a.state}</span>
      ),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Fixed assets"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/assets/new">Acquire asset</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={4}>
        <label className="block text-xs">
          Kind
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={kind}
            onChange={(e) => updateParam("kind", e.target.value)}
            data-testid="filter-kind"
          >
            <option value="">All</option>
            <option value="tangible">Tangible</option>
            <option value="intangible">Intangible</option>
          </select>
        </label>
        <label className="block text-xs">
          Class
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={assetClass}
            onChange={(e) => updateParam("asset_class", e.target.value)}
            data-testid="filter-class"
          >
            <option value="">All</option>
            <option value="machine">Machine</option>
            <option value="printer">Printer</option>
            <option value="computer">Computer</option>
            <option value="furniture">Furniture</option>
            <option value="vehicle">Vehicle</option>
            <option value="software">Software</option>
            <option value="intellectual_property">IP</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={state}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="disposed">Disposed</option>
            <option value="written_off">Written off</option>
          </select>
        </label>
        <label className="block text-xs">
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="filter-search"
            placeholder="name / number / serial"
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
        getRowKey={(a) => a.id}
        loading={loading && items.length === 0}
        emptyMessage="No assets match these filters."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
