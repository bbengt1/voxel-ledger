/**
 * `/expense-claims` — submitter view (my claims) by default; admin view
 * (`?all=true`) shows everything, filtered by submitter_user_id + state.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type ExpenseClaimResponse = components["schemas"]["ExpenseClaimResponse"];

const STATES = [
  "draft",
  "submitted",
  "approved",
  "rejected",
  "reimbursed",
  "cancelled",
] as const;

const ADMIN_ROLES: readonly string[] = ["owner", "bookkeeper"];

export function ExpenseClaimsListPage() {
  const user = useAuthStore((s) => s.user);
  const role = user?.role;
  const isAdmin = role ? ADMIN_ROLES.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const all = params.get("all") === "true";
  const stateFilter = params.get("state") ?? "";
  const submitterFilter = params.get("submitter_user_id") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<ExpenseClaimResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (all) {
      if (submitterFilter) q["submitter_user_id"] = submitterFilter;
    } else if (user?.id) {
      q["submitter_user_id"] = user.id;
    }
    return q;
  }, [stateFilter, submitterFilter, all, user?.id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/expense-claims", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load claims.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<ExpenseClaimResponse>[] = [
    {
      key: "claim_number",
      header: "Claim #",
      isPrimary: true,
      cell: (c) => (
        <Link
          to={`/expense-claims/${c.id}`}
          className="font-mono text-xs hover:underline"
        >
          {c.claim_number}
        </Link>
      ),
    },
    {
      key: "submitted",
      header: "Submitted",
      cell: (c) =>
        c.submitted_at
          ? new Date(c.submitted_at).toLocaleDateString()
          : "—",
    },
    {
      key: "total",
      header: "Total",
      align: "right",
      cell: (c) => <span className="font-mono">${c.total_amount}</span>,
    },
    { key: "state", header: "State", cell: (c) => c.state },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Expense claims"
        actions={
          <Button asChild>
            <Link to="/expense-claims/new">New claim</Link>
          </Button>
        }
      />

      <FilterBar columns={3}>
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
        {isAdmin ? (
          <>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={all}
                onChange={(e) => updateParam("all", e.target.checked ? "true" : "")}
                data-testid="filter-all"
              />
              Show all claims
            </label>
            {all ? (
              <label className="block text-xs">
                Submitter user id
                <Input
                  value={submitterFilter}
                  onChange={(e) =>
                    updateParam("submitter_user_id", e.target.value)
                  }
                  placeholder="uuid"
                  data-testid="filter-submitter"
                />
              </label>
            ) : null}
          </>
        ) : null}
      </FilterBar>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(c) => c.id}
        loading={loading && items.length === 0}
        emptyMessage="No claims yet."
        minWidthClassName="min-w-[560px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
