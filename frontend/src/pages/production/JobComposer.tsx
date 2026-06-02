/**
 * `/production/jobs/new` — compose a job that produces a **Part**
 * (assembly-line epic #267, Phase 4). Pick a part + quantity; the print
 * recipe comes from the part (shown read-only). Live cost is the part's
 * cost across the produced pieces, debounced on change.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { EntityPicker, type EntityOption } from "@/components/inventory/EntityPicker";
import { LiveCostPanel } from "@/components/production/LiveCostPanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type CalcResult = components["schemas"]["CalcResultResponse"];
type CalcInputs = components["schemas"]["CalcInputsPayload"];
type JobResponse = components["schemas"]["JobResponse"];
type PartResponse = components["schemas"]["PartResponse"];

const CALC_DEBOUNCE_MS = 300;

function parseIntSafe(s: string, fallback = 0): number {
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : fallback;
}

export function JobComposerPage() {
  const navigate = useNavigate();

  const [part, setPart] = useState<EntityOption | null>(null);
  const [partDetail, setPartDetail] = useState<PartResponse | null>(null);
  const [description, setDescription] = useState("");
  const [quantityOrdered, setQuantityOrdered] = useState("1");
  const [priority, setPriority] = useState("0");
  const [dueAt, setDueAt] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [calcResult, setCalcResult] = useState<CalcResult | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);

  // Fetch the selected part's full recipe (for the read-only display + the
  // live-cost inputs).
  useEffect(() => {
    if (!part) {
      setPartDetail(null);
      return;
    }
    let cancelled = false;
    apiClient
      .get<PartResponse>(`/api/v1/parts/${part.id}`)
      .then((res) => {
        if (!cancelled) setPartDetail(res.data);
      })
      .catch(() => {
        if (!cancelled) setPartDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [part]);

  // Build live-cost inputs from the part recipe + quantity (one plate =
  // the part). Null when there's nothing to cost yet.
  const calcInputs = useMemo<CalcInputs | null>(() => {
    const qty = parseIntSafe(quantityOrdered, 0);
    if (!partDetail || qty <= 0) return null;
    return {
      quantity_ordered: qty,
      plates: [
        {
          parts_per_set: partDetail.parts_per_run,
          print_minutes: partDetail.print_minutes,
          setup_minutes: partDetail.setup_minutes,
          print_grams_by_material: partDetail.print_grams_by_material ?? {},
          assigned_printer_ids: partDetail.assigned_printer_ids ?? [],
        },
      ],
    };
  }, [partDetail, quantityOrdered]);

  const calcHash = useMemo(
    () => (calcInputs ? JSON.stringify(calcInputs) : ""),
    [calcInputs],
  );
  const lastRequestId = useRef(0);

  useEffect(() => {
    if (!calcInputs) {
      setCalcResult(null);
      setCalcError(null);
      setCalcLoading(false);
      return;
    }
    const handle = window.setTimeout(() => {
      const id = ++lastRequestId.current;
      setCalcLoading(true);
      setCalcError(null);
      apiClient
        .post<CalcResult>("/api/v1/jobs/calculate", { inputs: calcInputs })
        .then((res) => {
          if (id === lastRequestId.current) setCalcResult(res.data);
        })
        .catch((err: unknown) => {
          if (id !== lastRequestId.current) return;
          const detail = (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail;
          setCalcError(typeof detail === "string" ? detail : "Could not calculate cost.");
        })
        .finally(() => {
          if (id === lastRequestId.current) setCalcLoading(false);
        });
    }, CALC_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calcHash]);

  async function submit(alsoSubmitToQueue: boolean) {
    if (!part) {
      setSubmitError("Pick a part first.");
      return;
    }
    const qty = parseIntSafe(quantityOrdered, 0);
    if (qty <= 0) {
      setSubmitError("Quantity must be at least 1.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const body: Record<string, unknown> = {
        part_id: part.id,
        quantity_ordered: qty,
        priority: parseIntSafe(priority, 0),
      };
      if (dueAt) body["due_at"] = new Date(dueAt).toISOString();
      const trimmedDescription = description.trim();
      if (trimmedDescription) body["description"] = trimmedDescription;
      const trimmedNotes = notes.trim();
      if (trimmedNotes) body["notes"] = trimmedNotes;

      const res = await apiClient.post<JobResponse>("/api/v1/jobs", body);
      if (alsoSubmitToQueue) {
        await apiClient.post(`/api/v1/jobs/${res.data.id}/submit`);
      }
      navigate(`/production/jobs/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data
        ?.detail;
      setSubmitError(typeof detail === "string" ? detail : "Could not save job.");
    } finally {
      setSubmitting(false);
    }
  }

  const gramsSum = partDetail
    ? Object.values(partDetail.print_grams_by_material ?? {}).reduce(
        (acc, g) => acc + (Number.parseFloat(g) || 0),
        0,
      )
    : 0;

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">New job</h1>
        </header>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Job details</h2>

          <label className="block text-sm">
            Part
            <EntityPicker
              kind="part"
              value={part}
              onChange={setPart}
              data-testid="job-part-picker"
            />
            {!part ? (
              <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>No matching part? Create one in the catalog.</span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => navigate("/catalog/parts/new")}
                  data-testid="job-create-part"
                >
                  Create part
                </Button>
              </div>
            ) : null}
          </label>

          {partDetail ? (
            <div
              className="rounded-md bg-muted/30 p-3 text-xs text-muted-foreground"
              data-testid="job-part-recipe"
            >
              <p className="font-medium text-foreground">Print recipe (from part)</p>
              <p>
                {partDetail.parts_per_run} part(s)/run · {partDetail.print_minutes} print min ·{" "}
                {partDetail.setup_minutes} setup min · Σ {gramsSum.toFixed(1)} g filament
              </p>
            </div>
          ) : null}

          <label className="block text-sm">
            Description
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              data-testid="job-description-input"
            />
          </label>
          <div className="grid grid-cols-3 gap-3">
            <label className="block text-sm">
              Quantity
              <Input
                type="number"
                min={1}
                value={quantityOrdered}
                onChange={(e) => setQuantityOrdered(e.target.value)}
                data-testid="job-qty-input"
              />
            </label>
            <label className="block text-sm">
              Priority
              <Input
                type="number"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                data-testid="job-priority-input"
              />
            </label>
            <label className="block text-sm">
              Due
              <Input
                type="date"
                value={dueAt}
                onChange={(e) => setDueAt(e.target.value)}
                data-testid="job-due-input"
              />
            </label>
          </div>
          <label className="block text-sm">
            Notes
            <textarea
              className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              data-testid="job-notes-input"
            />
          </label>
        </div>

        {submitError ? (
          <p role="alert" data-testid="composer-error" className="text-sm text-destructive">
            {submitError}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button
            type="button"
            disabled={submitting}
            onClick={() => void submit(false)}
            data-testid="save-draft-btn"
          >
            {submitting ? "Saving…" : "Save as draft"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={submitting}
            onClick={() => void submit(true)}
            data-testid="save-submit-btn"
          >
            Save and submit to queue
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={submitting}
            onClick={() => navigate("/production/jobs")}
          >
            Cancel
          </Button>
        </div>
      </div>

      <LiveCostPanel result={calcResult} loading={calcLoading} error={calcError} />
    </section>
  );
}
