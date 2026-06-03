/**
 * `/production/jobs` — list of jobs with URL-state-backed filters
 * (state, product id, customer free text, due-range).
 *
 * Replaces the stub list from Phase 5.1.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
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
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = role ? CAN_CREATE.includes(role) : false;
  const [duplicatingId, setDuplicatingId] = useState<string | null>(null);

  async function duplicateJob(jobId: string) {
    setDuplicatingId(jobId);
    try {
      const res = await apiClient.post<JobResponse>(
        `/api/v1/jobs/${jobId}/duplicate`,
      );
      navigate(`/production/jobs/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not duplicate job.";
      setError(typeof detail === "string" ? detail : "Could not duplicate job.");
      setDuplicatingId(null);
    }
  }

  const [params, setParams] = useSearchParams();
  // Default to in-progress jobs; the explicit "all" sentinel (vs. an absent
  // param) lets the user widen to every state without it snapping back.
  const stateFilter = params.get("state") ?? "in_progress";
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
    if (stateFilter && stateFilter !== "all") q["state"] = stateFilter;
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

  const columns: DataTableColumn<JobResponse>[] = [
    {
      key: "job_number",
      header: "Job #",
      isPrimary: true,
      cell: (j) => (
        <Link
          to={`/production/jobs/${j.id}`}
          className="font-mono text-xs hover:underline"
        >
          {j.job_number}
        </Link>
      ),
    },
    {
      key: "part",
      header: "Part",
      cell: (j) => (
        <span title={j.part_sku ?? undefined}>
          {j.part_name || j.part_sku || "—"}
        </span>
      ),
    },
    {
      key: "description",
      header: "Description",
      cell: (j) => <span title={j.description ?? undefined}>{j.description || "—"}</span>,
    },
    { key: "state", header: "State", cell: (j) => j.state },
    { key: "qty", header: "Qty", cell: (j) => j.quantity_ordered },
    { key: "pieces", header: "Pieces", cell: (j) => j.pieces_produced },
    { key: "priority", header: "Priority", cell: (j) => j.priority },
    {
      key: "due",
      header: "Due",
      cell: (j) => (j.due_at ? new Date(j.due_at).toLocaleDateString() : "—"),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cardFullWidth: true,
      cell: (j) =>
        canCreate ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => void duplicateJob(j.id)}
            disabled={duplicatingId === j.id}
            data-testid={`duplicate-job-${j.id}`}
          >
            {duplicatingId === j.id ? "Duplicating…" : "Duplicate"}
          </Button>
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Jobs"
        actions={
          canCreate ? (
            <Button asChild>
              <Link to="/production/jobs/new">New job</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={5}>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={stateFilter}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="all">All</option>
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
      </FilterBar>

      {error ? (
        <div
          role="alert"
          data-testid="jobs-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={filtered}
        getRowKey={(j) => j.id}
        loading={loading && items.length === 0}
        emptyMessage="No jobs match these filters."
        minWidthClassName="min-w-[760px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
