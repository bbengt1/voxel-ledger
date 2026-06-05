import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { ProductImage } from "@/components/catalog/ProductImage";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { ColumnPicker } from "@/components/ui/ColumnPicker";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { formatCurrency, useCurrency } from "@/lib/currency";
import { useColumnVisibility, type ColumnDef } from "@/lib/useColumnVisibility";
import { useAuthStore } from "@/store/useAuthStore";

type ProductResponse = components["schemas"]["ProductResponse"];

const DEBOUNCE_MS = 250;

const CAN_WRITE_ROLES = ["owner", "production", "sales"] as const;

const PRODUCT_COLUMNS: ColumnDef[] = [
  { id: "thumbnail", label: "Image" },
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

  const allColumns: (DataTableColumn<ProductResponse> & { id: string })[] = [
    {
      id: "thumbnail",
      key: "thumbnail",
      header: "Image",
      cell: (p) => (
        <ProductImage
          productId={p.id}
          size="thumb"
          className="h-9 w-9 shrink-0"
          alt={`${p.name} thumbnail`}
        />
      ),
    },
    {
      id: "sku",
      key: "sku",
      header: "SKU",
      isPrimary: true,
      cellClassName: "font-mono text-xs",
      cell: (p) => (
        <Link to={`/catalog/products/${p.id}`} className="hover:underline">
          {p.sku}
        </Link>
      ),
    },
    {
      id: "upc",
      key: "upc",
      header: "UPC",
      cellClassName: "font-mono text-xs text-muted-foreground",
      cell: (p) => <span data-testid={`product-upc-${p.id}`}>{p.upc ?? "—"}</span>,
    },
    { id: "name", key: "name", header: "Name", cell: (p) => p.name },
    {
      id: "price",
      key: "price",
      header: "Price",
      align: "right",
      cell: (p) => formatCurrency(p.unit_price, currency),
    },
    {
      id: "cost",
      key: "cost",
      header: "Cost (BOM)",
      align: "right",
      cell: (p) => (
        <span data-testid={`product-cost-${p.id}`}>
          {p.unit_cost_cached ? formatCurrency(p.unit_cost_cached, currency) : "—"}
        </span>
      ),
    },
    {
      id: "on_hand",
      key: "on_hand",
      header: "On hand",
      align: "right",
      cellClassName: "tabular-nums",
      cell: (p) => (
        <span data-testid={`product-on-hand-${p.id}`}>
          {Math.trunc(Number(p.total_on_hand ?? 0))}
        </span>
      ),
    },
    {
      id: "category",
      key: "category",
      header: "Category",
      cell: (p) => p.category ?? "—",
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
        title="Products"
        actions={
          <>
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
          </>
        }
      />

      <FilterBar columns={3}>
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
      </FilterBar>

      {error ? (
        <div
          role="alert"
          data-testid="products-error"
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
        emptyMessage="No products match the current filters."
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
