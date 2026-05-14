import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

const DEBOUNCE_MS = 250;
const CAN_WRITE_ROLES = ["owner", "production"] as const;

const KIND_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "All kinds" },
  { value: "workshop", label: "Workshop" },
  { value: "finished_goods", label: "Finished goods" },
  { value: "staging", label: "Staging" },
  { value: "customer_pickup", label: "Customer pickup" },
  { value: "consignment", label: "Consignment" },
  { value: "virtual", label: "Virtual" },
];

export function LocationsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<string>("");
  const [archivedFilter, setArchivedFilter] = useState<"" | "true" | "false">(
    "false",
  );
  const [items, setItems] = useState<InventoryLocationResponse[]>([]);
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
  }, [search, kindFilter, archivedFilter]);

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (search) p["search"] = search;
    if (kindFilter) p["kind"] = kindFilter;
    if (archivedFilter !== "") p["is_archived"] = archivedFilter;
    if (cursor) p["cursor"] = cursor;
    return p;
  }, [search, kindFilter, archivedFilter, cursor]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/inventory/locations", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
        setNextCursor(res.data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load inventory locations.";
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
        <h1 className="text-xl font-semibold">Inventory locations</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/inventory/locations/new">New location</Link>
          </Button>
        ) : null}
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="locations-search" className="text-xs font-medium">
            Search
          </label>
          <Input
            id="locations-search"
            placeholder="name or code"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="locations-kind" className="text-xs font-medium">
            Kind
          </label>
          <select
            id="locations-kind"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="locations-archived" className="text-xs font-medium">
            Status
          </label>
          <select
            id="locations-archived"
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
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="locations-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Code</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Kind</th>
            <th className="py-2 pr-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={4} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={4} className="py-4 text-center text-muted-foreground">
                No locations match the current filters.
              </td>
            </tr>
          ) : (
            items.map((loc) => (
              <tr key={loc.id} className="border-b border-border/50">
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link
                    to={`/inventory/locations/${loc.id}`}
                    className="hover:underline"
                  >
                    {loc.code}
                  </Link>
                </td>
                <td className="py-2 pr-2">{loc.name}</td>
                <td className="py-2 pr-2">{loc.kind}</td>
                <td className="py-2 pr-2">
                  {loc.is_archived ? "Archived" : "Active"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

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
