/**
 * `/catalog/parts` — Parts catalog list (assembly-line epic #267, Phase 1b).
 * Mirrors the Products list: search, archived filter, per-user column
 * visibility. Cost shows "—" until the Phase 2 rollup populates it.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { ColumnPicker } from "@/components/ui/ColumnPicker";
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
  const colCount = PART_COLUMNS.filter((c) => isVisible(c.id)).length;

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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Parts</h1>
        <div className="flex items-center gap-2">
          <ColumnPicker columns={PART_COLUMNS} isVisible={isVisible} toggle={toggle} />
          {canWrite ? (
            <Button asChild>
              <Link to="/catalog/parts/new">New part</Link>
            </Button>
          ) : null}
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-3">
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
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="parts-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            {isVisible("sku") ? <th className="py-2 pr-2">SKU</th> : null}
            {isVisible("name") ? <th className="py-2 pr-2">Name</th> : null}
            {isVisible("print_minutes") ? (
              <th className="py-2 pr-2 text-right">Print min</th>
            ) : null}
            {isVisible("parts_per_run") ? (
              <th className="py-2 pr-2 text-right">Parts/run</th>
            ) : null}
            {isVisible("cost") ? <th className="py-2 pr-2">Cost</th> : null}
            {isVisible("status") ? <th className="py-2 pr-2">Status</th> : null}
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={colCount} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={colCount} className="py-4 text-center text-muted-foreground">
                No parts match the current filters.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr key={p.id} className="border-b border-border/50">
                {isVisible("sku") ? (
                  <td className="py-2 pr-2 font-mono text-xs">
                    <Link to={`/catalog/parts/${p.id}`} className="hover:underline">
                      {p.sku}
                    </Link>
                  </td>
                ) : null}
                {isVisible("name") ? <td className="py-2 pr-2">{p.name}</td> : null}
                {isVisible("print_minutes") ? (
                  <td className="py-2 pr-2 text-right tabular-nums">{p.print_minutes}</td>
                ) : null}
                {isVisible("parts_per_run") ? (
                  <td className="py-2 pr-2 text-right tabular-nums">{p.parts_per_run}</td>
                ) : null}
                {isVisible("cost") ? (
                  <td className="py-2 pr-2" data-testid={`part-cost-${p.id}`}>
                    {p.unit_cost_cached
                      ? formatCurrency(p.unit_cost_cached, currency)
                      : "—"}
                  </td>
                ) : null}
                {isVisible("status") ? (
                  <td className="py-2 pr-2">{p.is_archived ? "Archived" : "Active"}</td>
                ) : null}
              </tr>
            ))
          )}
        </tbody>
      </table>

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
