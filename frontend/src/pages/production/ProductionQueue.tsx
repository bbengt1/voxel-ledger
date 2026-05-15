/**
 * `/production/queue` — production-order board.
 *
 * Left column: production orders (selectable cards). Right column: the
 * jobs in the selected order, drag-to-reorder. "New production order"
 * button (owner + production). "Add job" picker pulls from queued jobs
 * not yet on this order.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import { useAuthStore } from "@/store/useAuthStore";

type ProductionOrderResponse =
  components["schemas"]["ProductionOrderResponse"];
type JobResponse = components["schemas"]["JobResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "production"];

const STATE_BADGE: Record<ProductionOrderResponse["state"], string> = {
  planning: "bg-muted text-foreground",
  active: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100",
  completed: "bg-slate-200 text-slate-900 dark:bg-slate-800 dark:text-slate-100",
  archived: "bg-muted text-muted-foreground",
};

export function ProductionQueuePage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [orders, setOrders] = useState<ProductionOrderResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [jobsById, setJobsById] = useState<Record<string, JobResponse>>({});
  const [queuedJobs, setQueuedJobs] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerJobId, setPickerJobId] = useState("");

  const refetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/production-orders", { params: {} });
      setOrders(res.data.items);
      if (!selectedId && res.data.items.length > 0) {
        setSelectedId(res.data.items[0]?.id ?? null);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Failed to load production orders.",
      );
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void refetchOrders();
  }, [refetchOrders]);

  // Fetch queued jobs once for the picker.
  useEffect(() => {
    api
      .get("/api/v1/jobs", { params: { state: "queued" } })
      .then((res) => setQueuedJobs(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  // Fetch each job referenced by the selected order so we can render
  // pieces_produced / quantity_ordered.
  const selectedOrder = useMemo(
    () => orders.find((o) => o.id === selectedId) ?? null,
    [orders, selectedId],
  );

  useEffect(() => {
    if (!selectedOrder) return;
    const missing = (selectedOrder.jobs ?? [])
      .map((m) => m.job_id)
      .filter((id) => !(id in jobsById));
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(
      missing.map((id) =>
        api
          .get(`/api/v1/jobs/${id}` as "/api/v1/jobs/{job_id}", {})
          .then((res) => res.data as unknown as JobResponse)
          .catch(() => null),
      ),
    ).then((results) => {
      if (cancelled) return;
      setJobsById((prev) => {
        const next = { ...prev };
        for (const j of results) {
          if (j) next[j.id] = j;
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [selectedOrder, jobsById]);

  async function createOrder(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const res = await apiClient.post<ProductionOrderResponse>(
        "/api/v1/production-orders",
        { name: newName.trim(), priority: 0 },
      );
      setNewName("");
      setCreating(false);
      setSelectedId(res.data.id);
      await refetchOrders();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not create order.");
    } finally {
      setBusy(false);
    }
  }

  async function addJob() {
    if (!selectedId || !pickerJobId) return;
    setBusy(true);
    try {
      await apiClient.post(
        `/api/v1/production-orders/${selectedId}/jobs`,
        { job_id: pickerJobId },
      );
      setPickerOpen(false);
      setPickerJobId("");
      await refetchOrders();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not add job.");
    } finally {
      setBusy(false);
    }
  }

  async function removeJob(jobId: string) {
    if (!selectedId) return;
    setBusy(true);
    try {
      await apiClient.delete(
        `/api/v1/production-orders/${selectedId}/jobs/${jobId}`,
      );
      await refetchOrders();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not remove job.");
    } finally {
      setBusy(false);
    }
  }

  async function reorder(jobId: string, newPosition: number) {
    if (!selectedId) return;
    setBusy(true);
    try {
      await apiClient.patch(
        `/api/v1/production-orders/${selectedId}/jobs`,
        { job_id: jobId, new_position: newPosition },
      );
      await refetchOrders();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not reorder.");
    } finally {
      setBusy(false);
    }
  }

  async function transitionOrder(path: "activate" | "complete" | "archive") {
    if (!selectedId) return;
    setBusy(true);
    try {
      await apiClient.post(
        `/api/v1/production-orders/${selectedId}/${path}`,
      );
      await refetchOrders();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : `Could not ${path}.`);
    } finally {
      setBusy(false);
    }
  }

  async function actOnJob(job: JobResponse) {
    setBusy(true);
    try {
      let path: "submit" | "start" | "complete";
      if (job.state === "draft") path = "submit";
      else if (job.state === "queued") path = "start";
      else if (job.state === "in_progress") path = "complete";
      else return;
      await apiClient.post(`/api/v1/jobs/${job.id}/${path}`);
      const res = await api.get(
        `/api/v1/jobs/${job.id}` as "/api/v1/jobs/{job_id}",
        {},
      );
      setJobsById((prev) => ({
        ...prev,
        [job.id]: res.data as unknown as JobResponse,
      }));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not advance job.",
      );
    } finally {
      setBusy(false);
    }
  }

  const sortedMembers = useMemo(() => {
    if (!selectedOrder) return [];
    return [...(selectedOrder.jobs ?? [])].sort(
      (a, b) => a.display_order - b.display_order,
    );
  }, [selectedOrder]);

  const eligibleQueuedJobs = useMemo(() => {
    const inOrder = new Set(sortedMembers.map((m) => m.job_id));
    return queuedJobs.filter((j) => !inOrder.has(j.id));
  }, [queuedJobs, sortedMembers]);

  return (
    <section className="flex h-full gap-4">
      <aside className="w-72 flex-shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Production orders</h2>
          {canWrite ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setCreating((s) => !s)}
              data-testid="new-order-btn"
            >
              New
            </Button>
          ) : null}
        </div>

        {creating ? (
          <form
            onSubmit={createOrder}
            className="flex flex-col gap-2 rounded-md border border-border p-2"
          >
            <Input
              placeholder="Order name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              autoFocus
              data-testid="new-order-name-input"
            />
            <div className="flex gap-2">
              <Button
                type="submit"
                size="sm"
                disabled={busy}
                data-testid="new-order-submit"
              >
                Create
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setCreating(false);
                  setNewName("");
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="rounded border border-destructive bg-destructive/10 p-2 text-xs text-destructive"
            data-testid="queue-error"
          >
            {error}
          </div>
        ) : null}

        {loading && orders.length === 0 ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : orders.length === 0 ? (
          <p className="text-xs text-muted-foreground">No production orders.</p>
        ) : (
          <ul className="space-y-2" data-testid="orders-list">
            {orders.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(o.id)}
                  className={cn(
                    "w-full rounded-md border border-border p-2 text-left text-sm transition-colors",
                    selectedId === o.id
                      ? "border-primary bg-accent"
                      : "hover:bg-accent/50",
                  )}
                  data-testid={`order-${o.id}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{o.name}</span>
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 text-xs",
                        STATE_BADGE[o.state],
                      )}
                    >
                      {o.state}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {o.order_number} · {(o.jobs ?? []).length} jobs
                    {o.due_at
                      ? ` · due ${new Date(o.due_at).toLocaleDateString()}`
                      : ""}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <div className="flex-1 space-y-3 border-l border-border pl-4">
        {selectedOrder ? (
          <>
            <header className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold">{selectedOrder.name}</h2>
                <p className="text-xs text-muted-foreground">
                  {selectedOrder.order_number}
                </p>
              </div>
              {canWrite ? (
                <div className="flex gap-2">
                  {selectedOrder.state === "planning" ? (
                    <Button
                      size="sm"
                      onClick={() => void transitionOrder("activate")}
                      disabled={busy}
                      data-testid="order-activate"
                    >
                      Activate
                    </Button>
                  ) : null}
                  {selectedOrder.state === "active" ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void transitionOrder("complete")}
                      disabled={busy}
                      data-testid="order-complete"
                    >
                      Complete
                    </Button>
                  ) : null}
                  {selectedOrder.state !== "archived" ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => void transitionOrder("archive")}
                      disabled={busy}
                      data-testid="order-archive"
                    >
                      Archive
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </header>

            {canWrite ? (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setPickerOpen((s) => !s)}
                  data-testid="add-job-btn"
                >
                  Add job
                </Button>
                {pickerOpen ? (
                  <div className="flex flex-1 items-center gap-2">
                    <select
                      className="h-9 flex-1 rounded-md border border-input bg-background px-2 text-sm"
                      value={pickerJobId}
                      onChange={(e) => setPickerJobId(e.target.value)}
                      data-testid="add-job-select"
                    >
                      <option value="">Select queued job…</option>
                      {eligibleQueuedJobs.map((j) => (
                        <option key={j.id} value={j.id}>
                          {j.job_number} (qty {j.quantity_ordered})
                        </option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      onClick={() => void addJob()}
                      disabled={!pickerJobId || busy}
                      data-testid="add-job-confirm"
                    >
                      Add
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}

            <ol className="space-y-2" data-testid="order-jobs">
              {sortedMembers.length === 0 ? (
                <li className="text-sm text-muted-foreground">
                  No jobs on this order yet.
                </li>
              ) : (
                sortedMembers.map((m, idx) => {
                  const j = jobsById[m.job_id];
                  const progressPct =
                    j && j.quantity_ordered > 0
                      ? Math.min(
                          100,
                          Math.round((j.pieces_produced / j.quantity_ordered) * 100),
                        )
                      : 0;
                  let actionLabel: string | null = null;
                  if (j?.state === "draft") actionLabel = "Submit";
                  else if (j?.state === "queued") actionLabel = "Start";
                  else if (j?.state === "in_progress") actionLabel = "Complete";
                  return (
                    <li
                      key={m.job_id}
                      className="flex items-center gap-3 rounded-md border border-border p-2"
                      data-testid={`order-job-${m.job_id}`}
                      draggable={canWrite}
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", m.job_id);
                      }}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const draggedId = e.dataTransfer.getData("text/plain");
                        if (draggedId && draggedId !== m.job_id) {
                          void reorder(draggedId, idx);
                        }
                      }}
                    >
                      <span className="cursor-grab text-muted-foreground" aria-hidden="true">
                        ⋮⋮
                      </span>
                      <div className="flex-1 text-sm">
                        <div className="font-mono text-xs">
                          {j?.job_number ?? m.job_id.slice(0, 8)}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {j?.state ?? "loading…"} · {j?.pieces_produced ?? 0}/
                          {j?.quantity_ordered ?? "?"}
                        </div>
                        {j ? (
                          <div
                            className="mt-1 h-1 w-full overflow-hidden rounded bg-muted"
                            aria-hidden="true"
                          >
                            <div
                              className="h-full bg-emerald-500"
                              style={{ width: `${progressPct}%` }}
                            />
                          </div>
                        ) : null}
                      </div>
                      {canWrite && j && actionLabel ? (
                        <Button
                          size="sm"
                          onClick={() => void actOnJob(j)}
                          disabled={busy}
                          data-testid={`order-job-${m.job_id}-action`}
                        >
                          {actionLabel}
                        </Button>
                      ) : null}
                      {canWrite ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => void removeJob(m.job_id)}
                          disabled={busy}
                          data-testid={`order-job-${m.job_id}-remove`}
                          aria-label="Remove job from order"
                        >
                          ×
                        </Button>
                      ) : null}
                    </li>
                  );
                })
              )}
            </ol>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Select a production order to see its jobs.
          </p>
        )}
      </div>
    </section>
  );
}
