/**
 * `/catalog/labels` — print barcode labels for selected products.
 *
 * Pick one or more products, set the per-product copy count, and the
 * page lays them out as an Avery-5160-style 3×10 sheet (30 labels per
 * page, 1" × 2-5/8" each). Hit **Print** and the browser dialog turns
 * it into a PDF or sends it to a real printer.
 *
 * Layout is all CSS — no PDF lib on the server. The barcode is an
 * SVG component that renders the product's existing UPC-A. Products
 * without a UPC render with name/SKU/price only.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { UpcaBarcode } from "@/components/catalog/UpcaBarcode";
import {
  EntityPicker,
  type EntityOption,
} from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { formatCurrency, useCurrency } from "@/lib/currency";
import { findTemplate, useLabelTemplate } from "@/lib/labelTemplates";

type ProductResponse = components["schemas"]["ProductResponse"];

interface LabelRow {
  key: string;
  productId: string;
  quantity: number;
  /** Filled in once the product detail fetch completes. */
  product: ProductResponse | null;
}

let _key = 0;
const nextKey = () => `k${++_key}`;

type LabelMode = "labels" | "scan_sheet";

export function ProductLabelsPage() {
  const currency = useCurrency();
  const configuredTemplate = useLabelTemplate();
  // Two modes: regular labels honor the operator's configured
  // template; the scan sheet always uses Avery 5163 (2" × 4", 10 per
  // sheet) since the bigger cells fit a readable name + big barcode
  // for tabletop scanning at the POS.
  const [mode, setMode] = useState<LabelMode>("labels");
  const template =
    mode === "scan_sheet" ? findTemplate("avery_5163") : configuredTemplate;
  const [rows, setRows] = useState<LabelRow[]>([
    { key: nextKey(), productId: "", quantity: 1, product: null },
  ]);
  const [showName, setShowName] = useState(true);
  const [showPrice, setShowPrice] = useState(true);
  const [showSku, setShowSku] = useState(true);

  // Whenever a row's productId is set but ``product`` isn't loaded
  // yet, fetch the product. The picker only carries id+label.
  useEffect(() => {
    let cancelled = false;
    const missing = rows.filter((r) => r.productId && !r.product);
    if (missing.length === 0) return;
    Promise.all(
      missing.map((r) =>
        apiClient
          .get<ProductResponse>(`/api/v1/products/${r.productId}`)
          .then((res) => ({ key: r.key, product: res.data }))
          .catch(() => null),
      ),
    ).then((results) => {
      if (cancelled) return;
      setRows((prev) =>
        prev.map((row) => {
          const hit = results.find((r) => r && r.key === row.key);
          return hit ? { ...row, product: hit.product } : row;
        }),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [rows]);

  function setProduct(key: string, opt: EntityOption | null) {
    setRows((prev) =>
      prev.map((r) =>
        r.key === key
          ? { ...r, productId: opt?.id ?? "", product: null }
          : r,
      ),
    );
  }
  function setQuantity(key: string, qty: number) {
    setRows((prev) =>
      prev.map((r) =>
        r.key === key ? { ...r, quantity: Math.max(1, qty || 1) } : r,
      ),
    );
  }
  function addRow() {
    setRows((prev) => [
      ...prev,
      { key: nextKey(), productId: "", quantity: 1, product: null },
    ]);
  }
  function removeRow(key: string) {
    setRows((prev) =>
      prev.length > 1 ? prev.filter((r) => r.key !== key) : prev,
    );
  }

  // "Load all" pulls the full active-products list (paginated) and
  // creates one row per product, qty 1. Each row's ``product`` field
  // is populated inline from the list response so we skip the
  // per-row detail-fetch effect entirely.
  const [loadingAll, setLoadingAll] = useState(false);
  async function loadAllProducts() {
    setLoadingAll(true);
    try {
      const collected: ProductResponse[] = [];
      let cursor: string | null = null;
      // Hard cap: 500 products is more than any single-page sheet
      // would ever sanely produce; bail out before we DDoS ourselves.
      const HARD_CAP = 500;
      while (collected.length < HARD_CAP) {
        const params: Record<string, string> = { is_archived: "false", limit: "100" };
        if (cursor) params["cursor"] = cursor;
        const res = await apiClient.get<{
          items: ProductResponse[];
          next_cursor: string | null;
        }>("/api/v1/products", { params });
        collected.push(...res.data.items);
        if (!res.data.next_cursor) break;
        cursor = res.data.next_cursor;
      }
      setRows(
        collected.length > 0
          ? collected.map((p) => ({
              key: nextKey(),
              productId: p.id,
              quantity: 1,
              product: p,
            }))
          : [{ key: nextKey(), productId: "", quantity: 1, product: null }],
      );
    } finally {
      setLoadingAll(false);
    }
  }

  function clearAll() {
    setRows([{ key: nextKey(), productId: "", quantity: 1, product: null }]);
  }

  // Entering scan-sheet mode auto-fills with every active product at
  // qty 1 — the whole point of the mode is "one tile per product the
  // cashier can scan from a printed binder."
  useEffect(() => {
    if (mode === "scan_sheet") void loadAllProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  function setAllQuantities(qty: number) {
    setRows((prev) =>
      prev.map((r) => ({ ...r, quantity: Math.max(1, qty || 1) })),
    );
  }

  // Expand selected rows into a flat list of label cells. Each row
  // contributes ``quantity`` copies. Products that haven't loaded yet
  // are skipped (they'll appear once their fetch resolves).
  const labels: ProductResponse[] = [];
  for (const r of rows) {
    if (!r.product) continue;
    for (let i = 0; i < r.quantity; i++) labels.push(r.product);
  }
  const totalLabels = labels.length;

  return (
    <section className="flex flex-col gap-4 print:gap-0">
      <header className="flex flex-wrap items-end justify-between gap-2 print:hidden">
        <div>
          <h1 className="text-xl font-semibold">
            {mode === "scan_sheet" ? "POS scan sheet" : "Product labels"}
          </h1>
          <p className="mt-1 text-xs text-muted-foreground">
            {mode === "scan_sheet"
              ? `${template.name} — auto-loads every active product, one tile each. Print and keep at the POS for products without an affixed label.`
              : `${template.name} — ${template.cols * template.rows} labels per page. Change the template in Admin → Settings.`}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div
            role="tablist"
            aria-label="Output mode"
            className="inline-flex rounded-md border border-border p-0.5"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mode === "labels"}
              onClick={() => setMode("labels")}
              className={
                "rounded px-3 py-1 text-xs " +
                (mode === "labels"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground")
              }
              data-testid="labels-mode-labels"
            >
              Labels
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "scan_sheet"}
              onClick={() => setMode("scan_sheet")}
              className={
                "rounded px-3 py-1 text-xs " +
                (mode === "scan_sheet"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground")
              }
              data-testid="labels-mode-scan-sheet"
            >
              POS scan sheet
            </button>
          </div>
          <Button
            type="button"
            onClick={() => window.print()}
            disabled={totalLabels === 0}
            data-testid="labels-print"
          >
            Print {totalLabels > 0 ? `(${totalLabels})` : ""}
          </Button>
        </div>
      </header>

      {mode === "scan_sheet" ? (
        <div
          className="rounded-lg border border-border p-4 print:hidden"
          data-testid="scan-sheet-info"
        >
          <h2 className="text-sm font-semibold">Scan sheet</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Auto-loaded {totalLabels}{" "}
            {totalLabels === 1 ? "product" : "products"}. Each tile shows
            the product name, SKU, and a scannable UPC barcode. Pages
            are sized for an Avery 5163 sheet (2″ × 4″, 10 per page).
          </p>
        </div>
      ) : (
      <div className="rounded-lg border border-border p-4 print:hidden">
        <h2 className="text-sm font-semibold">Products</h2>
        <ul className="mt-3 flex flex-col gap-2">
          {rows.map((r) => (
            <li key={r.key} className="flex items-end gap-2">
              <div className="flex-1">
                <EntityPicker
                  kind="product"
                  value={
                    r.product
                      ? { id: r.product.id, label: r.product.name }
                      : r.productId
                        ? { id: r.productId, label: "(loading…)" }
                        : null
                  }
                  onChange={(opt) => setProduct(r.key, opt)}
                  data-testid={`labels-product-${r.key}`}
                />
              </div>
              <label className="text-xs">
                Copies
                <Input
                  type="number"
                  min={1}
                  step={1}
                  className="w-20"
                  value={r.quantity}
                  onChange={(e) => setQuantity(r.key, Number(e.target.value))}
                  data-testid={`labels-qty-${r.key}`}
                />
              </label>
              {rows.length > 1 ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => removeRow(r.key)}
                >
                  ×
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={addRow}>
              + Add product
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => void loadAllProducts()}
              disabled={loadingAll}
              data-testid="labels-load-all"
            >
              {loadingAll ? "Loading…" : "Load all products"}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={clearAll}
              disabled={
                rows.length === 1 && !rows[0].productId
              }
              data-testid="labels-clear-all"
            >
              Clear
            </Button>
            <label className="flex items-center gap-1 text-muted-foreground">
              Set copies for all:
              <Input
                type="number"
                min={1}
                step={1}
                defaultValue={1}
                className="ml-1 h-7 w-16"
                onBlur={(e) => setAllQuantities(Number(e.target.value))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    setAllQuantities(
                      Number((e.target as HTMLInputElement).value),
                    );
                  }
                }}
                data-testid="labels-bulk-qty"
              />
            </label>
          </div>
          <div className="flex items-center gap-3 text-muted-foreground">
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={showName}
                onChange={(e) => setShowName(e.target.checked)}
              />
              Name
            </label>
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={showSku}
                onChange={(e) => setShowSku(e.target.checked)}
              />
              SKU
            </label>
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={showPrice}
                onChange={(e) => setShowPrice(e.target.checked)}
              />
              Price
            </label>
          </div>
        </div>
      </div>
      )}

      {/* Print sheet. CSS handles the 3-column layout and the @page
          paper size; non-print viewports get a centered preview. The
          'labels-print-root' wrapper is what the @media print rules
          use to hide everything else on the page. */}
      <div className="labels-print-root" data-mode={mode}>
      <div className="labels-sheet">
        {totalLabels === 0 ? (
          <p className="rounded border border-dashed border-border p-6 text-center text-sm text-muted-foreground print:hidden">
            Pick at least one product to preview labels.
          </p>
        ) : null}
        {labels.map((p, idx) => (
          <div
            key={`${p.id}-${idx}`}
            className="label-cell"
            data-testid={`label-cell-${idx}`}
          >
            {mode === "scan_sheet" || showName ? (
              <div className="label-name">{p.name}</div>
            ) : null}
            <div className="label-barcode">
              {p.upc ? (
                <UpcaBarcode value={p.upc} height={24} />
              ) : (
                <span className="text-[8px] text-muted-foreground">
                  No UPC
                </span>
              )}
            </div>
            <div className="label-footer">
              {mode === "scan_sheet" || showSku ? (
                <span className="label-sku">{p.sku}</span>
              ) : null}
              {mode === "scan_sheet" || showPrice ? (
                <span className="label-price">
                  {formatCurrency(p.unit_price, currency)}
                </span>
              ) : null}
            </div>
          </div>
        ))}
      </div>
      </div>

      <style>{`
        /* Layout driven by the configured label template (see
           lib/labelTemplates.ts). Columns are sized explicitly (not
           1fr) so they line up with the physical sheet regardless of
           viewport width. */
        .labels-sheet {
          display: grid;
          grid-template-columns: repeat(${template.cols}, ${template.labelWidth});
          column-gap: ${template.columnGap};
          row-gap: ${template.rowGap};
          width: ${template.sheetContentWidth};
          margin: 0 auto;
        }
        /* 3-row grid inside each label so the barcode row gets a
           guaranteed '1fr' height — that's what lets the SVG stretch
           to the full label area. Pure flex + percentage heights
           collapse the SVG in some browsers. */
        .label-cell {
          width: ${template.labelWidth};
          height: ${template.labelHeight};
          padding: 0.05in 0.08in;
          box-sizing: border-box;
          display: grid;
          grid-template-rows: auto 1fr auto;
          gap: 0.02in;
          page-break-inside: avoid;
          break-inside: avoid;
          overflow: hidden;
        }
        .label-name {
          font-size: 9px;
          font-weight: 600;
          line-height: 1.05;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .label-barcode {
          min-height: 0;
          min-width: 0;
        }
        /* preserveAspectRatio='none' on the SVG plus 100% width/
           height stretches the bars horizontally to fill the label.
           UPC-A scanners read on relative bar widths, which are
           preserved; the result is a slightly wider-than-spec
           printout that still scans. */
        .label-barcode svg {
          display: block;
          width: 100%;
          height: 100%;
        }
        .label-footer {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          font-size: 8px;
          font-family: ui-monospace, SFMono-Regular, monospace;
          line-height: 1;
        }
        .label-price {
          font-weight: 600;
        }
        /* Scan-sheet mode: bigger cells (2" × 4" Avery 5163) deserve
           bigger type and a taller barcode so a cashier can read and
           scan from a few feet away. */
        .labels-print-root[data-mode="scan_sheet"] .label-name {
          font-size: 14px;
          line-height: 1.2;
          white-space: normal;
          overflow: hidden;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
        }
        .labels-print-root[data-mode="scan_sheet"] .label-cell {
          padding: 0.12in 0.16in;
        }
        .labels-print-root[data-mode="scan_sheet"] .label-footer {
          font-size: 11px;
        }
        /* Non-print preview gets a faint dashed border so the operator
           sees the label boundaries. The print path removes them. */
        @media screen {
          .label-cell {
            border: 1px dashed #d4d4d8;
          }
        }
        @media print {
          @page {
            size: ${template.pageSize};
            margin: ${template.pageMarginV} ${template.pageMarginH};
          }
          /* Hide everything by default — the AppShell sidebar, topbar,
             and outer padding all leak into the page otherwise. The
             'labels-print-root' wrapper opts back in just for the
             sheet itself. */
          html, body, #root {
            background: white !important;
            margin: 0 !important;
            padding: 0 !important;
          }
          body * {
            visibility: hidden !important;
          }
          .labels-print-root,
          .labels-print-root * {
            visibility: visible !important;
          }
          .labels-print-root {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
          }
          .labels-sheet {
            margin: 0;
            width: ${template.sheetContentWidth};
          }
          .label-cell {
            border: none;
          }
        }
      `}</style>
    </section>
  );
}
