/**
 * `/recurring-bills` — list of recurring bill templates. URL-state-
 * backed. Mirrors RecurringList (AR side).
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { useAuthStore } from "@/store/useAuthStore";

type RecurringBillTemplateResponse =
  components["schemas"]["RecurringBillTemplateResponse"];

const STATES = ["active", "paused", "cancelled"] as const;
const CAN_CREATE: readonly string[] = ["owner", "bookkeeper"];

export function RecurringBillsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const vendorId = params.get("vendor_id") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<RecurringBillTemplateResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (vendorId) q["vendor_id"] = vendorId;
    return q;
  }, [stateFilter, vendorId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/recurring-bills", { params: query })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(
          typeof detail === "string"
            ? detail
            : "Failed to load recurring bills.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  const columns: DataTableColumn<RecurringBillTemplateResponse>[] = [
    {
      key: "name",
      header: "Name",
      isPrimary: true,
      cell: (t) => (
        <Link to={`/recurring-bills/${t.id}`} className="hover:underline">
          {t.name}
        </Link>
      ),
    },
    {
      key: "vendor",
      header: "Vendor",
      cell: (t) => (
        <span className="font-mono text-xs">{t.vendor_id.slice(0, 8)}</span>
      ),
    },
    {
      key: "cadence",
      header: "Cadence",
      cell: (t) => `every ${t.cadence_interval} ${t.cadence_kind}`,
    },
    {
      key: "next_issue",
      header: "Next issue",
      cell: (t) => new Date(t.next_issue_at).toLocaleDateString(),
    },
    {
      key: "auto_issue",
      header: "Auto-issue",
      cell: (t) => (t.auto_issue ? "yes" : "no"),
    },
    { key: "state", header: "State", cell: (t) => t.state },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Recurring bills"
        actions={
          canCreate ? (
            <Button asChild>
              <Link to="/recurring-bills/new">New recurring</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={2}>
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
        getRowKey={(t) => t.id}
        loading={loading && items.length === 0}
        emptyMessage="No recurring bills match."
        minWidthClassName="min-w-[720px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
