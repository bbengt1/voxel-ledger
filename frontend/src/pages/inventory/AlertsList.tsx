/**
 * Low-stock alerts view.
 *
 * The backend returns alerts already sorted by deficit DESC. We expose
 * a sortable header so users can also sort by name/threshold/on-hand
 * client-side, but the default lines up with the API.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type LowStockAlertResponse = components["schemas"]["LowStockAlertResponse"];
type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

type EntityKind = LowStockAlertResponse["entity_kind"];

type SortKey = "deficit" | "entity_name" | "threshold" | "total_on_hand";

const ENTITY_LABEL: Record<EntityKind, string> = {
  material: "M",
  supply: "S",
  product: "P",
};

export function AlertsListPage() {
  const [items, setItems] = useState<LowStockAlertResponse[]>([]);
  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);
  const [entityKind, setEntityKind] = useState<EntityKind | "">("");
  const [locationId, setLocationId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("deficit");
  const [sortDesc, setSortDesc] = useState(true);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ items: InventoryLocationResponse[] }>(
        "/api/v1/inventory/locations",
        { params: { is_archived: "false" } },
      )
      .then((res) => {
        if (cancelled) return;
        setLocations(res.data.items);
      })
      .catch(() => {
        if (!cancelled) setLocations([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (entityKind) params["entity_kind"] = entityKind;
    if (locationId) params["location_id"] = locationId;
    apiClient
      .get<{ items: LowStockAlertResponse[] }>(
        "/api/v1/inventory/alerts/low-stock",
        { params },
      )
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load alerts.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityKind, locationId]);

  const sortedItems = useMemo(() => {
    const arr = [...items];
    arr.sort((a, b) => {
      let cmp: number;
      if (sortKey === "entity_name") {
        cmp = a.entity_name.localeCompare(b.entity_name);
      } else {
        cmp = Number(a[sortKey]) - Number(b[sortKey]);
      }
      return sortDesc ? -cmp : cmp;
    });
    return arr;
  }, [items, sortKey, sortDesc]);

  function toggleSort(k: SortKey) {
    if (k === sortKey) setSortDesc((d) => !d);
    else {
      setSortKey(k);
      setSortDesc(true);
    }
  }

  function entityHref(it: LowStockAlertResponse): string {
    if (it.entity_kind === "material")
      return `/catalog/materials/${it.entity_id}`;
    if (it.entity_kind === "supply")
      return `/catalog/supplies/${it.entity_id}`;
    return `/catalog/products/${it.entity_id}`;
  }

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Low-stock alerts</h1>
      </header>

      <div className="rounded-md border border-border bg-muted/20 p-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium">
            Entity kind
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={entityKind}
              onChange={(e) => setEntityKind(e.target.value as EntityKind | "")}
              data-testid="alerts-filter-kind"
            >
              <option value="">All</option>
              <option value="material">Material</option>
              <option value="supply">Supply</option>
              <option value="product">Product</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium">
            Location
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              data-testid="alerts-filter-location"
            >
              <option value="">All locations</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="alerts-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      {!loading && sortedItems.length === 0 ? (
        <div
          data-testid="alerts-empty"
          className="rounded-md border border-border bg-muted/20 p-6 text-center"
        >
          <p className="text-base font-medium">All stocked up.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Entities without a configured threshold never appear here. Set
            thresholds on the catalog detail page&apos;s on-hand section.
          </p>
        </div>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="py-2 pr-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSort("entity_name")}
                  data-testid="sort-name"
                >
                  Entity
                </Button>
              </th>
              <th className="py-2 pr-2 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSort("threshold")}
                  data-testid="sort-threshold"
                >
                  Threshold
                </Button>
              </th>
              <th className="py-2 pr-2 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSort("total_on_hand")}
                  data-testid="sort-on-hand"
                >
                  On hand
                </Button>
              </th>
              <th className="py-2 pr-2 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSort("deficit")}
                  data-testid="sort-deficit"
                >
                  Deficit
                </Button>
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && sortedItems.length === 0 ? (
              <tr>
                <td
                  colSpan={4}
                  className="py-4 text-center text-muted-foreground"
                >
                  Loading…
                </td>
              </tr>
            ) : (
              sortedItems.map((it) => (
                <tr
                  key={`${it.entity_kind}:${it.entity_id}`}
                  className="border-b border-border/50"
                  data-testid={`alert-row-${it.entity_id}`}
                >
                  <td className="py-2 pr-2">
                    <span
                      className="mr-1 inline-block rounded bg-muted px-1 text-xs font-mono"
                      aria-label={`${it.entity_kind} entity`}
                    >
                      {ENTITY_LABEL[it.entity_kind]}
                    </span>
                    <Link to={entityHref(it)} className="hover:underline">
                      {it.entity_name}
                    </Link>
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    {it.threshold}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    {it.total_on_hand}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums text-destructive">
                    {it.deficit}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}
    </section>
  );
}
