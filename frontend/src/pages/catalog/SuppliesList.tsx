import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type SupplyResponse = components["schemas"]["SupplyResponse"];

const DEBOUNCE_MS = 250;
const CAN_WRITE_ROLES = ["owner", "production"] as const;

export function SuppliesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [archivedFilter, setArchivedFilter] = useState<"" | "true" | "false">(
    "false",
  );
  const [items, setItems] = useState<SupplyResponse[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
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
      .get("/api/v1/supplies", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
        setNextCursor(res.data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load supplies.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params]);

  const columns: DataTableColumn<SupplyResponse>[] = [
    {
      key: "name",
      header: "Name",
      isPrimary: true,
      cell: (s) => (
        <Link to={`/catalog/supplies/${s.id}`} className="hover:underline">
          {s.name}
        </Link>
      ),
    },
    { key: "unit", header: "Unit", cell: (s) => s.unit },
    {
      key: "pieces_per_unit",
      header: "Pieces / unit",
      cell: (s) => (
        <span data-testid="pieces-per-unit-cell">{s.pieces_per_unit ?? "—"}</span>
      ),
    },
    { key: "unit_cost", header: "Unit cost", align: "right", cell: (s) => s.unit_cost },
    { key: "vendor", header: "Vendor", cell: (s) => s.vendor ?? "—" },
    {
      key: "on_hand",
      header: "On hand",
      cell: (s) => (
        <span data-testid="on-hand-cell">
          {Math.trunc(Number(s.total_on_hand))} {s.unit}
          {s.pieces_per_unit
            ? ` (${
                Math.trunc(Number(s.total_on_hand)) * s.pieces_per_unit
              } pieces)`
            : ""}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (s) => (s.is_archived ? "Archived" : "Active"),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Supplies"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/catalog/supplies/new">New supply</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={2}>
        <div className="flex flex-col gap-1">
          <label htmlFor="supplies-search" className="text-xs font-medium">
            Search
          </label>
          <Input
            id="supplies-search"
            placeholder="name, unit, vendor"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="supplies-archived" className="text-xs font-medium">
            Status
          </label>
          <select
            id="supplies-archived"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={archivedFilter}
            onChange={(e) =>
              setArchivedFilter(e.target.value as "" | "true" | "false")
            }
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
          data-testid="supplies-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(s) => s.id}
        loading={loading && items.length === 0}
        emptyMessage="No supplies match the current filters."
        minWidthClassName="min-w-[760px]"
      />

      {nextCursor ? (
        <div className="flex justify-end">
          <Button
            variant="outline"
            onClick={() => setCursor(nextCursor)}
            data-testid="load-more"
          >
            Load more
          </Button>
        </div>
      ) : null}
    </section>
  );
}
