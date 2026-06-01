/**
 * `/production/builds/:id` — build header, a live plan (required
 * parts/supplies + availability + cost), draft edit form, and
 * complete/cancel actions. Completing consumes the product's parts +
 * supplies and credits product stock (assembly-line epic #267, Phase 5).
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { BuildPlanPanel } from "@/components/production/BuildPlanPanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type BuildResponse = components["schemas"]["BuildResponse"];
type BuildPlan = components["schemas"]["BuildPlanResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "production"];

function fmtMoney(s: string | null | undefined): string {
  if (s === null || s === undefined) return "—";
  const n = Number.parseFloat(s);
  if (Number.isNaN(n)) return s;
  return `$${n.toFixed(2)}`;
}

function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  if (typeof detail === "string") return detail;
  // Insufficient-stock 409 carries { message, shortfalls }.
  if (detail && typeof detail === "object" && "message" in detail) {
    const msg = (detail as { message?: unknown }).message;
    if (typeof msg === "string") return msg;
  }
  return fallback;
}

export function BuildDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [build, setBuild] = useState<BuildResponse | null>(null);
  const [plan, setPlan] = useState<BuildPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [editing, setEditing] = useState(false);
  const [editQty, setEditQty] = useState("");
  const [editMinutes, setEditMinutes] = useState("");
  const [editNotes, setEditNotes] = useState("");

  const refetch = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<BuildResponse>(`/api/v1/builds/${id}`);
      setBuild(res.data);
    } catch (err: unknown) {
      setError(errorDetail(err, "Failed to load build."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  // Live plan (availability + cost) for the build.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setPlanLoading(true);
    apiClient
      .get<BuildPlan>(`/api/v1/builds/${id}/plan`)
      .then((res) => {
        if (!cancelled) setPlan(res.data);
      })
      .catch(() => {
        /* non-fatal */
      })
      .finally(() => {
        if (!cancelled) setPlanLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, build?.updated_at]);

  async function complete() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/builds/${id}/complete`);
      await refetch();
    } catch (err: unknown) {
      setError(errorDetail(err, "Could not complete build."));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/builds/${id}/cancel`);
      await refetch();
    } catch (err: unknown) {
      setError(errorDetail(err, "Could not cancel build."));
    } finally {
      setBusy(false);
    }
  }

  function startEdit() {
    if (!build) return;
    setEditQty(String(build.quantity));
    setEditMinutes(String(build.assembly_minutes));
    setEditNotes(build.notes ?? "");
    setEditing(true);
  }

  async function saveEdit() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      const qty = Number.parseInt(editQty, 10);
      if (Number.isFinite(qty) && qty > 0) body["quantity"] = qty;
      const mins = Number.parseInt(editMinutes, 10);
      if (Number.isFinite(mins) && mins >= 0) body["assembly_minutes"] = mins;
      body["notes"] = editNotes.trim() || null;
      await apiClient.patch(`/api/v1/builds/${id}`, body);
      setEditing(false);
      await refetch();
    } catch (err: unknown) {
      setError(errorDetail(err, "Could not save build."));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !build) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (error && !build) {
    return (
      <div role="alert" className="text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (!build) return null;

  const isDraft = build.state === "draft";
  const editable = canWrite && isDraft;

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold">Build {build.build_number}</h1>
            <p className="text-sm text-muted-foreground">
              State: <span data-testid="build-state">{build.state}</span> · Qty{" "}
              {build.quantity}
            </p>
            <p className="text-sm text-muted-foreground">
              Product:{" "}
              <Link
                to={`/catalog/products/${build.product_id}`}
                className="hover:underline"
                data-testid="build-product-link"
              >
                view product
              </Link>
            </p>
          </div>
          <Button variant="outline" asChild>
            <Link to="/production/builds">Back to builds</Link>
          </Button>
        </header>

        {error ? (
          <div role="alert" data-testid="build-detail-error" className="text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {canWrite && isDraft ? (
          <div className="flex flex-wrap gap-2" data-testid="build-actions">
            <Button
              disabled={busy || (plan ? !plan.can_build : false)}
              onClick={() => void complete()}
              data-testid="build-complete-btn"
            >
              Complete build
            </Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => void cancel()}
              data-testid="build-cancel-btn"
            >
              Cancel
            </Button>
            {plan && !plan.can_build ? (
              <span className="self-center text-xs text-destructive">
                Not enough stock to complete — see the build plan.
              </span>
            ) : null}
          </div>
        ) : null}

        {editable ? (
          <div className="rounded-lg border border-border p-4" data-testid="build-edit-section">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Build details</h2>
              {!editing ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={startEdit}
                  data-testid="build-edit-btn"
                >
                  Edit
                </Button>
              ) : null}
            </div>
            {editing ? (
              <div className="mt-3 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <label className="block text-sm">
                    Quantity
                    <Input
                      type="number"
                      min={1}
                      value={editQty}
                      onChange={(e) => setEditQty(e.target.value)}
                      data-testid="build-edit-qty"
                    />
                  </label>
                  <label className="block text-sm">
                    Assembly labor (min)
                    <Input
                      type="number"
                      min={0}
                      value={editMinutes}
                      onChange={(e) => setEditMinutes(e.target.value)}
                      data-testid="build-edit-minutes"
                    />
                  </label>
                </div>
                <label className="block text-sm">
                  Notes
                  <textarea
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    rows={2}
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    data-testid="build-edit-notes"
                  />
                </label>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    disabled={busy}
                    onClick={() => void saveEdit()}
                    data-testid="build-edit-save"
                  >
                    Save
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted-foreground">
                Quantity {build.quantity} · Assembly labor {build.assembly_minutes} min
              </p>
            )}
          </div>
        ) : null}

        {build.state === "completed" ? (
          <div className="rounded-lg border border-border p-4" data-testid="build-cost-summary">
            <h2 className="text-sm font-semibold">Cost (at completion)</h2>
            <dl className="mt-2 space-y-1 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Per unit</dt>
                <dd data-testid="build-unit-cost">{fmtMoney(build.unit_cost_cached)}</dd>
              </div>
              <div className="flex justify-between font-medium">
                <dt>Total</dt>
                <dd data-testid="build-total-cost">{fmtMoney(build.total_cost_cached)}</dd>
              </div>
            </dl>
          </div>
        ) : null}

        {build.notes ? (
          <div className="rounded-lg border border-border p-4">
            <h2 className="text-sm font-semibold">Notes</h2>
            <p className="whitespace-pre-wrap text-sm">{build.notes}</p>
          </div>
        ) : null}

        <p className="text-xs text-muted-foreground">
          <button
            type="button"
            className="hover:underline"
            onClick={() => navigate("/production/builds/new")}
          >
            Compose another build →
          </button>
        </p>
      </div>

      <BuildPlanPanel plan={plan} loading={planLoading} error={null} />
    </section>
  );
}
