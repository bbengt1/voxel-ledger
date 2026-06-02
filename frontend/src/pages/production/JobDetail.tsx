/**
 * `/production/jobs/:id` — job header, plates table with record-run, state
 * transition buttons gated by role + current state, and a read-only live
 * cost panel sourced from `POST /api/v1/jobs/calculate` with `{job_id}`.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { LiveCostPanel } from "@/components/production/LiveCostPanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type JobResponse = components["schemas"]["JobResponse"];
type CalcResult = components["schemas"]["CalcResultResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "production"];

interface Transition {
  label: string;
  path: string;
  variant?: "default" | "secondary" | "destructive";
  allowedStates: ReadonlyArray<JobResponse["state"]>;
}

const TRANSITIONS: readonly Transition[] = [
  {
    label: "Submit to queue",
    path: "submit",
    variant: "default",
    allowedStates: ["draft"],
  },
  {
    label: "Start",
    path: "start",
    variant: "default",
    allowedStates: ["queued"],
  },
  {
    label: "Complete",
    path: "complete",
    variant: "secondary",
    allowedStates: ["in_progress"],
  },
  {
    label: "Cancel",
    path: "cancel",
    variant: "destructive",
    allowedStates: ["draft", "queued", "in_progress"],
  },
];

export function JobDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [job, setJob] = useState<JobResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [calc, setCalc] = useState<CalcResult | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);

  // Job-level edit form (non-terminal jobs only).
  const [editingJob, setEditingJob] = useState(false);
  const [editQty, setEditQty] = useState("");
  const [editPriority, setEditPriority] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editDescription, setEditDescription] = useState("");

  // Inline per-plate edit.

  const refetch = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(
        `/api/v1/jobs/${id}` as "/api/v1/jobs/{job_id}",
        {},
      );
      // Cast through unknown for noUncheckedIndexedAccess narrowing.
      setJob(res.data as unknown as JobResponse);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load job.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  // Live cost calculation for the saved job.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setCalcLoading(true);
    apiClient
      .post<CalcResult>("/api/v1/jobs/calculate", { job_id: id })
      .then((res) => {
        if (!cancelled) setCalc(res.data);
      })
      .catch(() => {
        /* non-fatal */
      })
      .finally(() => {
        if (!cancelled) setCalcLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, job?.updated_at]);

  async function transition(path: string) {
    if (!id) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/jobs/${id}/${path}`);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : `Could not ${path} job.`,
      );
    } finally {
      setBusy(false);
    }
  }

  async function recordRun(plateId: string) {
    if (!id) return;
    setBusy(true);
    try {
      await apiClient.post(
        `/api/v1/jobs/${id}/plates/${plateId}/record-run`,
        { runs_completed_delta: 1 },
      );
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not record run.",
      );
    } finally {
      setBusy(false);
    }
  }

  function startEditJob() {
    if (!job) return;
    setEditQty(String(job.quantity_ordered));
    setEditPriority(String(job.priority));
    setEditNotes(job.notes ?? "");
    setEditDescription(job.description ?? "");
    setEditingJob(true);
  }

  async function saveJob() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      const qty = Number.parseInt(editQty, 10);
      if (Number.isFinite(qty) && qty > 0) body["quantity_ordered"] = qty;
      const pri = Number.parseInt(editPriority, 10);
      if (Number.isFinite(pri)) body["priority"] = pri;
      body["notes"] = editNotes.trim() || null;
      body["description"] = editDescription.trim() || null;
      await apiClient.patch(`/api/v1/jobs/${id}`, body);
      setEditingJob(false);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save job.");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !job) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (error && !job) {
    return (
      <div role="alert" className="text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (!job) return null;

  const allowedTransitions = TRANSITIONS.filter((t) =>
    t.allowedStates.includes(job.state),
  );

  // Completed/cancelled jobs are read-only; everything else is editable.
  const editable =
    canWrite && job.state !== "completed" && job.state !== "cancelled";

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold">
              Job {job.job_number}
            </h1>
            <p className="text-sm text-muted-foreground">
              State: <span data-testid="job-state">{job.state}</span> · Pieces{" "}
              {job.pieces_produced} / {job.quantity_ordered}
            </p>
            {job.part_id ? (
              <p className="text-sm text-muted-foreground">
                Part:{" "}
                <Link
                  to={`/catalog/parts/${job.part_id}`}
                  className="hover:underline"
                  data-testid="job-part-link"
                >
                  view part
                </Link>
              </p>
            ) : null}
          </div>
          <Button variant="outline" asChild>
            <Link to="/production/jobs">Back to jobs</Link>
          </Button>
        </header>

        {error ? (
          <div role="alert" className="text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {canWrite && allowedTransitions.length > 0 ? (
          <div className="flex flex-wrap gap-2" data-testid="job-transitions">
            {allowedTransitions.map((t) => (
              <Button
                key={t.path}
                variant={t.variant ?? "default"}
                disabled={busy}
                onClick={() => void transition(t.path)}
                data-testid={`transition-${t.path}`}
              >
                {t.label}
              </Button>
            ))}
          </div>
        ) : null}

        {editable ? (
          <div
            className="rounded-lg border border-border p-4"
            data-testid="job-edit-section"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Job details</h2>
              {!editingJob ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={startEditJob}
                  data-testid="job-edit-btn"
                >
                  Edit
                </Button>
              ) : null}
            </div>
            {editingJob ? (
              <div className="mt-3 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <label className="block text-sm">
                    Quantity
                    <Input
                      type="number"
                      min={1}
                      value={editQty}
                      onChange={(e) => setEditQty(e.target.value)}
                      data-testid="job-edit-qty"
                    />
                  </label>
                  <label className="block text-sm">
                    Priority
                    <Input
                      type="number"
                      value={editPriority}
                      onChange={(e) => setEditPriority(e.target.value)}
                      data-testid="job-edit-priority"
                    />
                  </label>
                </div>
                <label className="block text-sm">
                  Description
                  <Input
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    data-testid="job-edit-description"
                  />
                </label>
                <label className="block text-sm">
                  Notes
                  <textarea
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    rows={2}
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    data-testid="job-edit-notes"
                  />
                </label>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() => void saveJob()}
                    data-testid="job-edit-save"
                  >
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setEditingJob(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">
                {job.description ? <>{job.description} · </> : null}
                Quantity {job.quantity_ordered} · Priority {job.priority}
              </p>
            )}
          </div>
        ) : null}

        <div className="rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Plates</h2>
          <table className="mt-2 w-full table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-2">#</th>
                <th className="py-2 pr-2">Name</th>
                <th className="py-2 pr-2">Parts / set</th>
                <th className="py-2 pr-2">Runs</th>
                <th className="py-2 pr-2">Print min</th>
                <th className="py-2 pr-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {(job.plates ?? []).length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="py-4 text-center text-muted-foreground"
                  >
                    No plates on this job.
                  </td>
                </tr>
              ) : (
                (job.plates ?? []).map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-border/50"
                    data-testid={`plate-row-${p.id}`}
                  >
                    <td className="py-2 pr-2 font-mono text-xs">{p.plate_number}</td>
                    <td className="py-2 pr-2">{p.name}</td>
                    <td className="py-2 pr-2">{p.parts_per_set}</td>
                    <td className="py-2 pr-2">{p.runs_completed}</td>
                    <td className="py-2 pr-2">{p.print_minutes}</td>
                    <td className="py-2 pr-2 text-right">
                      {canWrite && job.state === "in_progress" ? (
                        <Button
                          size="sm"
                          disabled={busy}
                          onClick={() => void recordRun(p.id)}
                          data-testid={`record-run-${p.id}`}
                        >
                          Record run
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {job.notes ? (
          <div className="rounded-lg border border-border p-4">
            <h2 className="text-sm font-semibold">Notes</h2>
            <p className="whitespace-pre-wrap text-sm">{job.notes}</p>
          </div>
        ) : null}

        <p className="text-xs text-muted-foreground">
          <button
            type="button"
            className="hover:underline"
            onClick={() => navigate("/production/jobs/new")}
          >
            Compose another job →
          </button>
        </p>
      </div>

      <LiveCostPanel result={calc} loading={calcLoading} error={null} />
    </section>
  );
}
