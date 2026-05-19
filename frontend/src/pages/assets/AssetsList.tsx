/**
 * `/assets` — fixed-asset register (Phase 9.10a, #162).
 *
 * Filters by kind, asset_class, state, and free-text search. URL-state-
 * backed so deep links round-trip.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type AssetResponse = components["schemas"]["FixedAssetResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function AssetsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const assetClass = params.get("asset_class") ?? "";
  const state = params.get("state") ?? "";
  const search = params.get("search") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<AssetResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (kind) q["kind"] = kind;
    if (assetClass) q["asset_class"] = assetClass;
    if (state) q["state"] = state;
    if (search) q["search"] = search;
    return q;
  }, [kind, assetClass, state, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/fixed-assets", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load assets.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Fixed assets</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/assets/new">Acquire asset</Link>
          </Button>
        ) : null}
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="block text-xs">
          Kind
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={kind}
            onChange={(e) => updateParam("kind", e.target.value)}
            data-testid="filter-kind"
          >
            <option value="">All</option>
            <option value="tangible">Tangible</option>
            <option value="intangible">Intangible</option>
          </select>
        </label>
        <label className="block text-xs">
          Class
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={assetClass}
            onChange={(e) => updateParam("asset_class", e.target.value)}
            data-testid="filter-class"
          >
            <option value="">All</option>
            <option value="machine">Machine</option>
            <option value="printer">Printer</option>
            <option value="computer">Computer</option>
            <option value="furniture">Furniture</option>
            <option value="vehicle">Vehicle</option>
            <option value="software">Software</option>
            <option value="intellectual_property">IP</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={state}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="disposed">Disposed</option>
            <option value="written_off">Written off</option>
          </select>
        </label>
        <label className="block text-xs">
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="filter-search"
            placeholder="name / number / serial"
          />
        </label>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">#</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Class</th>
            <th className="py-2 pr-2">Cost</th>
            <th className="py-2 pr-2">Acquired</th>
            <th className="py-2 pr-2">State</th>
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
                No assets match these filters.
              </td>
            </tr>
          ) : (
            items.map((a) => (
              <tr
                key={a.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`asset-row-${a.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link to={`/assets/${a.id}`} className="hover:underline">
                    {a.asset_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">{a.name}</td>
                <td className="py-2 pr-2 text-xs">
                  {a.kind} · {a.asset_class}
                </td>
                <td className="py-2 pr-2">{a.acquisition_cost}</td>
                <td className="py-2 pr-2">{a.acquired_on}</td>
                <td className="py-2 pr-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {a.state}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
