/**
 * `/production/builds` — list of builds with a state filter. A build
 * assembles a Product from its Parts + Supplies (assembly-line epic
 * #267, Phase 5).
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type BuildResponse = components["schemas"]["BuildResponse"];

const STATES = ["draft", "completed", "cancelled"] as const;

const CAN_CREATE: readonly string[] = ["owner", "production"];

function fmtMoney(s: string | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const n = Number.parseFloat(s);
  if (Number.isNaN(n)) return s;
  return `$${n.toFixed(2)}`;
}

export function BuildsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<BuildResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    return q;
  }, [stateFilter]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/builds", { params: query })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load builds.");
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
        <h1 className="text-xl font-semibold">Builds</h1>
        {canCreate ? (
          <Button asChild>
            <Link to="/production/builds/new">New build</Link>
          </Button>
        ) : null}
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={stateFilter}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="build-filter-state"
          >
            <option value="">All</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="builds-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Build #</th>
            <th className="py-2 pr-2">State</th>
            <th className="py-2 pr-2">Qty</th>
            <th className="py-2 pr-2 text-right">Total cost</th>
            <th className="py-2 pr-2">Created</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                No builds match these filters.
              </td>
            </tr>
          ) : (
            items.map((b) => (
              <tr key={b.id} className="border-b border-border/50 hover:bg-accent/30">
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link to={`/production/builds/${b.id}`} className="hover:underline">
                    {b.build_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">{b.state}</td>
                <td className="py-2 pr-2">{b.quantity}</td>
                <td className="py-2 pr-2 text-right tabular-nums">
                  {fmtMoney(b.total_cost_cached)}
                </td>
                <td className="py-2 pr-2">{new Date(b.created_at).toLocaleDateString()}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
