/**
 * Read-only "On hand" section for the Part detail page (assembly-line
 * epic #267, Phase 6b). Parts are produced by **jobs** and consumed by
 * **builds**, never via manual transactions — so unlike
 * `OnHandSection` (material/supply/product) this has no record / adjust
 * / transfer actions. It just surfaces how many of the part are in stock
 * (total + per-location) so production can gauge availability before
 * composing a build.
 */
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

type OnHandListResponse = components["schemas"]["OnHandListResponse"];
type InventoryLocationResponse = components["schemas"]["InventoryLocationResponse"];

interface Props {
  partId: string;
  /** Bump to refetch (e.g. after a related change). */
  refreshKey?: number;
}

function fmtQty(qty: string | number): string {
  const n = Number(qty);
  if (Number.isNaN(n)) return String(qty);
  return String(n);
}

export function PartOnHandSection({ partId, refreshKey }: Props) {
  const [total, setTotal] = useState<string>("0");
  const [perLocation, setPerLocation] = useState<Record<string, string>>({});
  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<OnHandListResponse>("/api/v1/inventory/on-hand", {
        params: { entity_kind: "part", entity_id: partId },
      })
      .then((res) => {
        if (cancelled) return;
        const summary = (res.data.summaries ?? [])[0];
        if (summary) {
          setTotal(String(summary.total_on_hand));
          setPerLocation(
            Object.fromEntries(
              Object.entries(summary.per_location ?? {}).map(([k, v]) => [k, String(v)]),
            ),
          );
        } else {
          setTotal("0");
          setPerLocation({});
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTotal("0");
          setPerLocation({});
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [partId, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ items: InventoryLocationResponse[] }>("/api/v1/inventory/locations", {
        params: { is_archived: "false" },
      })
      .then((res) => {
        if (!cancelled) setLocations(res.data.items);
      })
      .catch(() => {
        if (!cancelled) setLocations([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const locationNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const loc of locations) m.set(loc.id, loc.name);
    return m;
  }, [locations]);

  const rows = useMemo(() => {
    return Object.entries(perLocation)
      .map(([locId, qty]) => ({
        id: locId,
        name: locationNameById.get(locId) ?? locId.slice(0, 8) + "…",
        qty,
      }))
      .sort((a, b) => Number(b.qty) - Number(a.qty));
  }, [perLocation, locationNameById]);

  return (
    <section
      className="space-y-2 rounded-lg border border-border p-4"
      data-testid="part-on-hand-section"
    >
      <div className="flex items-end justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">On hand</h2>
          <p className="text-2xl font-semibold" data-testid="part-on-hand-total">
            {loading ? "…" : fmtQty(total)}
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          Produced by jobs · consumed by builds
        </p>
      </div>

      {rows.length > 0 ? (
        <table
          className="w-full table-fixed border-collapse text-sm"
          data-testid="part-on-hand-per-location"
        >
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="py-2 pr-2">Location</th>
              <th className="py-2 pr-2 text-right">Quantity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border/50">
                <td className="py-1 pr-2">{r.name}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{fmtQty(r.qty)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-xs text-muted-foreground">No stock on hand yet.</p>
      )}
    </section>
  );
}
