/**
 * `/production/jobs` — list of jobs with URL-state-backed filters
 * (state, product id, customer free text, due-range).
 *
 * Replaces the stub list from Phase 5.1.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type JobResponse = components["schemas"]["JobResponse"];

const STATES = [
  "draft",
  "queued",
  "in_progress",
  "completed",
  "cancelled",
] as const;

const CAN_CREATE: readonly string[] = ["owner", "production"];

export function JobsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const productId = params.get("product_id") ?? "";
  const customer = params.get("customer") ?? "";
  const dueFrom = params.get("due_from") ?? "";
  const dueTo = params.get("due_to") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (productId) q["product_id"] = productId;
    return q;
  }, [stateFilter, productId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/jobs", { params: query })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load jobs.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  // Apply customer + due-range filters client-side (no backend support yet).
  const filtered = useMemo(() => {
    return items.filter((j) => {
      if (customer) {
        const hay = ((j.notes ?? "") + " " + (j.customer_id ?? "")).toLowerCase();
        if (!hay.includes(customer.toLowerCase())) return false;
      }
      if (dueFrom && j.due_at) {
        if (new Date(j.due_at) < new Date(dueFrom)) return false;
      }
      if (dueTo && j.due_at) {
        if (new Date(j.due_at) > new Date(dueTo)) return false;
      }
      return true;
    });
  }, [items, customer, dueFrom, dueTo]);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Jobs</h1>
        {canCreate ? (
          <Button asChild>
            <Link to="/production/jobs/new">New job</Link>
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
            data-testid="filter-state"
          >
            <option value="">All</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Product ID
          <Input
            value={productId}
            onChange={(e) => updateParam("product_id", e.target.value)}
            data-testid="filter-product"
          />
        </label>
        <label className="block text-xs">
          Customer
          <Input
            value={customer}
            onChange={(e) => updateParam("customer", e.target.value)}
            data-testid="filter-customer"
          />
        </label>
        <label className="block text-xs">
          Due from
          <Input
            type="date"
            value={dueFrom}
            onChange={(e) => updateParam("due_from", e.target.value)}
            data-testid="filter-due-from"
          />
        </label>
        <label className="block text-xs">
          Due to
          <Input
            type="date"
            value={dueTo}
            onChange={(e) => updateParam("due_to", e.target.value)}
            data-testid="filter-due-to"
          />
        </label>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="jobs-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Job #</th>
            <th className="py-2 pr-2">State</th>
            <th className="py-2 pr-2">Qty</th>
            <th className="py-2 pr-2">Pieces</th>
            <th className="py-2 pr-2">Priority</th>
            <th className="py-2 pr-2">Due</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : filtered.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No jobs match these filters.
              </td>
            </tr>
          ) : (
            filtered.map((j) => (
              <tr
                key={j.id}
                className="border-b border-border/50 hover:bg-accent/30"
              >
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link
                    to={`/production/jobs/${j.id}`}
                    className="hover:underline"
                  >
                    {j.job_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">{j.state}</td>
                <td className="py-2 pr-2">{j.quantity_ordered}</td>
                <td className="py-2 pr-2">{j.pieces_produced}</td>
                <td className="py-2 pr-2">{j.priority}</td>
                <td className="py-2 pr-2">
                  {j.due_at ? new Date(j.due_at).toLocaleDateString() : "—"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
