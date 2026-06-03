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

type MaterialResponse = components["schemas"]["MaterialResponse"];

const DEBOUNCE_MS = 250;

const CAN_WRITE_ROLES = ["owner", "production"] as const;

export function MaterialsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [archivedFilter, setArchivedFilter] = useState<"" | "true" | "false">(
    "false",
  );
  const [items, setItems] = useState<MaterialResponse[]>([]);
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
      .get("/api/v1/materials", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
        setNextCursor(res.data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load materials.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params]);

  const columns: DataTableColumn<MaterialResponse>[] = [
    {
      key: "name",
      header: "Name",
      isPrimary: true,
      cell: (m) => (
        <Link to={`/catalog/materials/${m.id}`} className="hover:underline">
          {m.name}
        </Link>
      ),
    },
    { key: "brand", header: "Brand", cell: (m) => m.brand ?? "—" },
    { key: "type", header: "Type", cell: (m) => m.material_type },
    { key: "color", header: "Color", cell: (m) => m.color ?? "—" },
    {
      key: "cost",
      header: "Cost/g",
      align: "right",
      cell: (m) => m.current_cost_per_gram,
    },
    {
      key: "on_hand",
      header: "On hand (g)",
      align: "right",
      cell: (m) => m.total_on_hand,
    },
    {
      key: "status",
      header: "Status",
      cell: (m) => (m.is_archived ? "Archived" : "Active"),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Materials"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/catalog/materials/new">New material</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={2}>
        <div className="flex flex-col gap-1">
          <label htmlFor="materials-search" className="text-xs font-medium">
            Search
          </label>
          <Input
            id="materials-search"
            placeholder="name, brand, type, color"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="materials-archived" className="text-xs font-medium">
            Status
          </label>
          <select
            id="materials-archived"
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
          data-testid="materials-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(m) => m.id}
        loading={loading && items.length === 0}
        emptyMessage="No materials match the current filters."
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
