/**
 * `/catalog/parts` — Parts catalog list (assembly-line epic #267, Phase 1b).
 * Mirrors the Products list: search, archived filter, per-user column
 * visibility. Cost shows "—" until the Phase 2 rollup populates it.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ColumnPicker } from "@/components/ui/ColumnPicker";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { formatCurrency, useCurrency } from "@/lib/currency";
import { useColumnVisibility, type ColumnDef } from "@/lib/useColumnVisibility";
import { useAuthStore } from "@/store/useAuthStore";

type PartResponse = components["schemas"]["PartResponse"];

const DEBOUNCE_MS = 250;
const CAN_WRITE_ROLES = ["owner", "production", "sales"] as const;

const PART_COLUMNS: ColumnDef[] = [
  { id: "sku", label: "SKU", alwaysVisible: true },
  { id: "name", label: "Name" },
  { id: "print_minutes", label: "Print min" },
  { id: "parts_per_run", label: "Parts/run" },
  { id: "cost", label: "Cost" },
  { id: "status", label: "Status" },
];

export function PartsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? (CAN_WRITE_ROLES as readonly string[]).includes(role) : false;
  const currency = useCurrency();
  const { isVisible, toggle } = useColumnVisibility("parts", PART_COLUMNS);

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [archivedFilter, setArchivedFilter] = useState<"" | "true" | "false">("false");
  const [items, setItems] = useState<PartResponse[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    setCursor(null);
  }, [search, archivedFilter]);

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (search) p["search"] = search;
    if (archivedFilter !== "") p["is_archived"] = archivedFilter;
    if (cursor) p["cursor"] = cursor;
    return p;
  }, [search, archivedFilter, cursor]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/parts", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
        setNextCursor(res.data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
          "Failed to load parts.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params]);

  const allColumns: (DataTableColumn<PartResponse> & { id: string })[] = [
    {
      id: "sku",
      key: "sku",
      header: "SKU",
      isPrimary: true,
      cellClassName: "font-mono text-xs",
      cell: (p) => (
        <Link to={`/catalog/parts/${p.id}`} className="hover:underline">
          {p.sku}
        </Link>
      ),
    },
    { id: "name", key: "name", header: "Name", cell: (p) => p.name },
    {
      id: "print_minutes",
      key: "print_minutes",
      header: "Print min",
      align: "right",
      cellClassName: "tabular-nums",
      cell: (p) => p.print_minutes,
    },
    {
      id: "parts_per_run",
      key: "parts_per_run",
      header: "Parts/run",
      align: "right",
      cellClassName: "tabular-nums",
      cell: (p) => p.parts_per_run,
    },
    {
      id: "cost",
      key: "cost",
      header: "Cost",
      align: "right",
      cell: (p) => (
        <span data-testid={`part-cost-${p.id}`}>
          {p.unit_cost_cached ? formatCurrency(p.unit_cost_cached, currency) : "—"}
        </span>
      ),
    },
    {
      id: "status",
      key: "status",
      header: "Status",
      cell: (p) => (p.is_archived ? "Archived" : "Active"),
    },
  ];
  const columns = allColumns.filter((c) => isVisible(c.id));

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Parts"
        actions={
          <>
            <ColumnPicker columns={PART_COLUMNS} isVisible={isVisible} toggle={toggle} />
            {canWrite ? (
              <Button asChild>
                <Link to="/catalog/parts/new">New part</Link>
              </Button>
            ) : null}
          </>
        }
      />

      <FilterBar columns={2}>
        <div className="flex flex-col gap-1">
          <label htmlFor="parts-search" className="text-xs font-medium">
            Search
          </label>
          <Input
            id="parts-search"
            placeholder="name or SKU"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="parts-archived" className="text-xs font-medium">
            Status
          </label>
          <select
            id="parts-archived"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={archivedFilter}
            onChange={(e) => setArchivedFilter(e.target.value as "" | "true" | "false")}
          >
            <option value="false">Active</option>
            <option value="true">Archived</option>
            <option value="">All</option>
          </select>
        </div>
      </FilterBar>

      {error ? (
        <div
          role="alert"
          data-testid="parts-error"
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
        emptyMessage="No parts match the current filters."
        minWidthClassName="min-w-[640px]"
      />

      {nextCursor ? (
        <div className="flex justify-end">
          <Button variant="outline" onClick={() => setCursor(nextCursor)} data-testid="load-more">
            Load more
          </Button>
        </div>
      ) : null}
    </section>
  );
}
