import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Supplies</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/catalog/supplies/new">New supply</Link>
          </Button>
        ) : null}
      </header>

      <div className="flex flex-wrap items-end gap-3">
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
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="supplies-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Unit</th>
            <th className="py-2 pr-2">Unit cost</th>
            <th className="py-2 pr-2">Vendor</th>
            <th className="py-2 pr-2">On hand</th>
            <th className="py-2 pr-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No supplies match the current filters.
              </td>
            </tr>
          ) : (
            items.map((s) => (
              <tr key={s.id} className="border-b border-border/50">
                <td className="py-2 pr-2">
                  <Link
                    to={`/catalog/supplies/${s.id}`}
                    className="hover:underline"
                  >
                    {s.name}
                  </Link>
                </td>
                <td className="py-2 pr-2">{s.unit}</td>
                <td className="py-2 pr-2">{s.unit_cost}</td>
                <td className="py-2 pr-2">{s.vendor ?? "—"}</td>
                <td className="py-2 pr-2">{s.total_on_hand}</td>
                <td className="py-2 pr-2">
                  {s.is_archived ? "Archived" : "Active"}
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
