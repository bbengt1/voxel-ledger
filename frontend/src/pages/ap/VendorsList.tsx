/**
 * `/vendors` — list with search + active/archived filter. URL-state-
 * backed, mirroring CustomersList.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type VendorResponse = components["schemas"]["VendorResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function VendorsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const state = params.get("state") ?? "active";
  const search = params.get("search") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<VendorResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (state) q["state"] = state;
    if (search) q["search"] = search;
    return q;
  }, [state, search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/vendors", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load vendors.");
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
        <h1 className="text-xl font-semibold">Vendors</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/vendors/new">New vendor</Link>
          </Button>
        ) : null}
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={state}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <label className="block text-xs">
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="filter-search"
            placeholder="name / number"
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
            <th className="py-2 pr-2">Email</th>
            <th className="py-2 pr-2">Terms</th>
            <th className="py-2 pr-2">State</th>
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
                No vendors match these filters.
              </td>
            </tr>
          ) : (
            items.map((v) => (
              <tr
                key={v.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`vendor-row-${v.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link to={`/vendors/${v.id}`} className="hover:underline">
                    {v.vendor_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">{v.display_name}</td>
                <td className="py-2 pr-2">{v.primary_email ?? "—"}</td>
                <td className="py-2 pr-2">{v.payment_terms_days}d</td>
                <td className="py-2 pr-2">{v.state}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
