/**
 * `/reports/inventory-valuation` — on-hand × cost-per-unit snapshot
 * (Phase 10.8b, #183). Optional location filter.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ReportResponse = components["schemas"]["InventoryValuationResponse"];
type LocationResponse = components["schemas"]["InventoryLocationResponse"];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export function InventoryValuationPage() {
  const [params, setParams] = useSearchParams();
  const asOf = params.get("as_of") ?? todayIso();
  const locationId = params.get("location_id") ?? "";

  const [locations, setLocations] = useState<LocationResponse[]>([]);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  useEffect(() => {
    api
      .get("/api/v1/inventory/locations")
      .then((res) => setLocations(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  useEffect(() => {
    const q: Record<string, string> = { as_of: asOf };
    if (locationId) q["location_id"] = locationId;
    api
      .get("/api/v1/reports/inventory-valuation", { params: q })
      .then((res) => setReport(res.data as ReportResponse))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load report.");
      });
  }, [asOf, locationId]);

  async function downloadCsv() {
    const q: Record<string, string> = { as_of: asOf, format: "csv" };
    if (locationId) q["location_id"] = locationId;
    const res = await apiClient.get("/api/v1/reports/inventory-valuation", {
      params: q,
      responseType: "blob",
    });
    const blob = new Blob([res.data as BlobPart], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `inventory-valuation-${asOf}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Inventory valuation</h1>
        <Button onClick={downloadCsv} data-testid="iv-csv">
          Download CSV
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block text-xs">
          As of
          <Input
            type="date"
            value={asOf}
            onChange={(e) => updateParam("as_of", e.target.value)}
            data-testid="iv-as-of"
          />
        </label>
        <label className="block text-xs">
          Location
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={locationId}
            onChange={(e) => updateParam("location_id", e.target.value)}
            data-testid="iv-location"
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

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[52rem] table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Location</th>
            <th className="py-2 pr-2">Kind</th>
            <th className="py-2 pr-2">SKU</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2 text-right">On hand</th>
            <th className="py-2 pr-2 text-right">Unit cost</th>
            <th className="py-2 pr-2 text-right">Valuation</th>
          </tr>
        </thead>
        <tbody>
          {report && report.rows.length ? (
            report.rows.map((r) => (
              <tr key={`${r.location_id}-${r.entity_id}`} className="border-b border-border/30">
                <td className="py-1 pr-2 text-xs">{r.location_name}</td>
                <td className="py-1 pr-2 text-xs">{r.entity_kind}</td>
                <td className="py-1 pr-2 font-mono text-xs">{r.sku ?? "—"}</td>
                <td className="py-1 pr-2">{r.name}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{r.on_hand}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{r.unit_cost}</td>
                <td className="py-1 pr-2 text-right tabular-nums font-medium">{r.valuation}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={7} className="py-4 text-center text-muted-foreground">
                No on-hand inventory.
              </td>
            </tr>
          )}
        </tbody>
        {report ? (
          <tfoot>
            <tr className="border-t-2 border-primary font-semibold">
              <td colSpan={6} className="py-2 pr-2">GRAND TOTAL</td>
              <td className="py-2 pr-2 text-right tabular-nums">{report.total_valuation}</td>
            </tr>
          </tfoot>
        ) : null}
      </table>
      </div>
    </section>
  );
}
