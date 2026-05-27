import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { formatCurrency, useCurrency } from "@/lib/currency";
import { useAuthStore } from "@/store/useAuthStore";

type ProductResponse = components["schemas"]["ProductResponse"];

const DEBOUNCE_MS = 250;

const CAN_WRITE_ROLES = ["owner", "production", "sales"] as const;

export function ProductsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;
  const currency = useCurrency();

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [archivedFilter, setArchivedFilter] = useState<"" | "true" | "false">(
    "false",
  );
  const [items, setItems] = useState<ProductResponse[]>([]);
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
  }, [search, category, archivedFilter]);

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (search) p["search"] = search;
    if (category) p["category"] = category;
    if (archivedFilter !== "") p["is_archived"] = archivedFilter;
    if (cursor) p["cursor"] = cursor;
    return p;
  }, [search, category, archivedFilter, cursor]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/products", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
        setNextCursor(res.data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load products.";
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
        <h1 className="text-xl font-semibold">Products</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/catalog/products/new">New product</Link>
          </Button>
        ) : null}
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="products-search" className="text-xs font-medium">
            Search
          </label>
          <Input
            id="products-search"
            placeholder="name, SKU, UPC"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="products-category" className="text-xs font-medium">
            Category
          </label>
          <Input
            id="products-category"
            placeholder="exact match"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="products-archived" className="text-xs font-medium">
            Status
          </label>
          <select
            id="products-archived"
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
          data-testid="products-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">SKU</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Price</th>
            <th className="py-2 pr-2 text-right">On hand</th>
            <th className="py-2 pr-2">Category</th>
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
                No products match the current filters.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr key={p.id} className="border-b border-border/50">
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link
                    to={`/catalog/products/${p.id}`}
                    className="hover:underline"
                  >
                    {p.sku}
                  </Link>
                </td>
                <td className="py-2 pr-2">{p.name}</td>
                <td className="py-2 pr-2">{formatCurrency(p.unit_price, currency)}</td>
                <td
                  className="py-2 pr-2 text-right tabular-nums"
                  data-testid={`product-on-hand-${p.id}`}
                >
                  {Math.trunc(Number(p.total_on_hand ?? 0))}
                </td>
                <td className="py-2 pr-2">{p.category ?? "—"}</td>
                <td className="py-2 pr-2">
                  {p.is_archived ? "Archived" : "Active"}
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
