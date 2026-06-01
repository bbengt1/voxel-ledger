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

type ProductResponse = components["schemas"]["ProductResponse"];

const DEBOUNCE_MS = 250;

const CAN_WRITE_ROLES = ["owner", "production", "sales"] as const;

const PRODUCT_COLUMNS: ColumnDef[] = [
  { id: "sku", label: "SKU", alwaysVisible: true },
  { id: "upc", label: "UPC" },
  { id: "name", label: "Name" },
  { id: "price", label: "Price" },
  { id: "cost", label: "Cost (BOM)" },
  { id: "on_hand", label: "On hand" },
  { id: "category", label: "Category" },
  { id: "status", label: "Status" },
];

export function ProductsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;
  const currency = useCurrency();
  const { isVisible, toggle } = useColumnVisibility("products", PRODUCT_COLUMNS);
  const colCount = PRODUCT_COLUMNS.filter((c) => isVisible(c.id)).length;

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
        <div className="flex items-center gap-2">
          <ColumnPicker
            columns={PRODUCT_COLUMNS}
            isVisible={isVisible}
            toggle={toggle}
          />
          {canWrite ? (
            <Button asChild>
              <Link to="/catalog/products/new">New product</Link>
            </Button>
          ) : null}
        </div>
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
            {isVisible("sku") ? <th className="py-2 pr-2">SKU</th> : null}
            {isVisible("upc") ? <th className="py-2 pr-2">UPC</th> : null}
            {isVisible("name") ? <th className="py-2 pr-2">Name</th> : null}
            {isVisible("price") ? <th className="py-2 pr-2">Price</th> : null}
            {isVisible("cost") ? <th className="py-2 pr-2">Cost (BOM)</th> : null}
            {isVisible("on_hand") ? (
              <th className="py-2 pr-2 text-right">On hand</th>
            ) : null}
            {isVisible("category") ? <th className="py-2 pr-2">Category</th> : null}
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
                No products match the current filters.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr key={p.id} className="border-b border-border/50">
                {isVisible("sku") ? (
                  <td className="py-2 pr-2 font-mono text-xs">
                    <Link
                      to={`/catalog/products/${p.id}`}
                      className="hover:underline"
                    >
                      {p.sku}
                    </Link>
                  </td>
                ) : null}
                {isVisible("upc") ? (
                  <td
                    className="py-2 pr-2 font-mono text-xs text-muted-foreground"
                    data-testid={`product-upc-${p.id}`}
                  >
                    {p.upc ?? "—"}
                  </td>
                ) : null}
                {isVisible("name") ? (
                  <td className="py-2 pr-2">{p.name}</td>
                ) : null}
                {isVisible("price") ? (
                  <td className="py-2 pr-2">
                    {formatCurrency(p.unit_price, currency)}
                  </td>
                ) : null}
                {isVisible("cost") ? (
                  <td className="py-2 pr-2" data-testid={`product-cost-${p.id}`}>
                    {p.unit_cost_cached
                      ? formatCurrency(p.unit_cost_cached, currency)
                      : "—"}
                  </td>
                ) : null}
                {isVisible("on_hand") ? (
                  <td
                    className="py-2 pr-2 text-right tabular-nums"
                    data-testid={`product-on-hand-${p.id}`}
                  >
                    {Math.trunc(Number(p.total_on_hand ?? 0))}
                  </td>
                ) : null}
                {isVisible("category") ? (
                  <td className="py-2 pr-2">{p.category ?? "—"}</td>
                ) : null}
                {isVisible("status") ? (
                  <td className="py-2 pr-2">
                    {p.is_archived ? "Archived" : "Active"}
                  </td>
                ) : null}
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
