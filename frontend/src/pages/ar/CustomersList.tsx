/**
 * `/customers` — list with search + active/archived filter. URL-state-
 * backed, mirroring the SalesList pattern.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { BatchOpsDialog } from "@/components/batch/BatchOpsDialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type CustomerResponse = components["schemas"]["CustomerResponse"];

const CAN_WRITE: readonly string[] = ["owner", "sales", "bookkeeper"];

export function CustomersListPage() {
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

  const [items, setItems] = useState<CustomerResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [batchOpen, setBatchOpen] = useState(false);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

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
      .get("/api/v1/customers", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(
          typeof detail === "string" ? detail : "Failed to load customers.",
        );
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
        <h1 className="text-xl font-semibold">Customers</h1>
        <div className="flex items-center gap-2">
          {canWrite && selected.size > 0 ? (
            <Button
              type="button"
              variant="outline"
              data-testid="customers-batch-archive"
              onClick={() => setBatchOpen(true)}
            >
              Archive {selected.size} selected
            </Button>
          ) : null}
          {canWrite ? (
            <Button asChild>
              <Link to="/customers/new">New customer</Link>
            </Button>
          ) : null}
        </div>
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
            {canWrite ? <th className="py-2 pr-2 w-6"></th> : null}
            <th className="py-2 pr-2">#</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Email</th>
            <th className="py-2 pr-2">Phone</th>
            <th className="py-2 pr-2">State</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={canWrite ? 6 : 5} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={canWrite ? 6 : 5} className="py-4 text-center text-muted-foreground">
                No customers match these filters.
              </td>
            </tr>
          ) : (
            items.map((c) => (
              <tr
                key={c.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`customer-row-${c.id}`}
              >
                {canWrite ? (
                  <td className="py-2 pr-2">
                    <input
                      type="checkbox"
                      data-testid={`customer-select-${c.id}`}
                      checked={selected.has(c.id)}
                      onChange={() => toggle(c.id)}
                    />
                  </td>
                ) : null}
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link to={`/customers/${c.id}`} className="hover:underline">
                    {c.customer_number}
                  </Link>
                </td>
                <td className="py-2 pr-2">{c.display_name}</td>
                <td className="py-2 pr-2">{c.primary_email ?? "—"}</td>
                <td className="py-2 pr-2">{c.phone ?? "—"}</td>
                <td className="py-2 pr-2">{c.state}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <BatchOpsDialog
        open={batchOpen}
        onOpenChange={setBatchOpen}
        entity="customer"
        action="archive"
        ids={Array.from(selected)}
        title={`Archive ${selected.size} customer${selected.size === 1 ? "" : "s"}`}
        onCommitted={() => {
          setSelected(new Set());
          setBatchOpen(false);
          // Re-fetch by toggling a state param so the existing effect re-runs.
          updateParam("state", state);
        }}
      />
    </section>
  );
}
