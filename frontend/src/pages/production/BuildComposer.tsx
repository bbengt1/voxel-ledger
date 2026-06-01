/**
 * `/production/builds/new` — compose a Build that assembles a Product
 * from its Parts + Supplies (assembly-line epic #267, Phase 5). Pick a
 * product + quantity; a debounced preview shows the required components
 * with on-hand availability + the rolled-up cost. Creating saves a
 * **draft** — stock is consumed later on the detail page (decision #3).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { EntityPicker, type EntityOption } from "@/components/inventory/EntityPicker";
import { BuildPlanPanel } from "@/components/production/BuildPlanPanel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type BuildResponse = components["schemas"]["BuildResponse"];
type BuildPlan = components["schemas"]["BuildPlanResponse"];

const PREVIEW_DEBOUNCE_MS = 300;

function parseIntSafe(s: string, fallback = 0): number {
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : fallback;
}

export function BuildComposerPage() {
  const navigate = useNavigate();

  const [product, setProduct] = useState<EntityOption | null>(null);
  const [quantity, setQuantity] = useState("1");
  const [assemblyMinutes, setAssemblyMinutes] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [plan, setPlan] = useState<BuildPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);

  const previewBody = useMemo(() => {
    const qty = parseIntSafe(quantity, 0);
    if (!product || qty <= 0) return null;
    const body: Record<string, unknown> = { product_id: product.id, quantity: qty };
    const am = assemblyMinutes.trim();
    if (am !== "") body["assembly_minutes"] = parseIntSafe(am, 0);
    return body;
  }, [product, quantity, assemblyMinutes]);

  const previewHash = useMemo(
    () => (previewBody ? JSON.stringify(previewBody) : ""),
    [previewBody],
  );
  const lastRequestId = useRef(0);

  useEffect(() => {
    if (!previewBody) {
      setPlan(null);
      setPlanError(null);
      setPlanLoading(false);
      return;
    }
    const handle = window.setTimeout(() => {
      const id = ++lastRequestId.current;
      setPlanLoading(true);
      setPlanError(null);
      apiClient
        .post<BuildPlan>("/api/v1/builds/preview", previewBody)
        .then((res) => {
          if (id === lastRequestId.current) setPlan(res.data);
        })
        .catch((err: unknown) => {
          if (id !== lastRequestId.current) return;
          const detail = (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail;
          setPlanError(typeof detail === "string" ? detail : "Could not build plan.");
        })
        .finally(() => {
          if (id === lastRequestId.current) setPlanLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewHash]);

  async function submit() {
    if (!product) {
      setSubmitError("Pick a product first.");
      return;
    }
    const qty = parseIntSafe(quantity, 0);
    if (qty <= 0) {
      setSubmitError("Quantity must be at least 1.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const body: Record<string, unknown> = { product_id: product.id, quantity: qty };
      const am = assemblyMinutes.trim();
      if (am !== "") body["assembly_minutes"] = parseIntSafe(am, 0);
      const trimmed = notes.trim();
      if (trimmed) body["notes"] = trimmed;
      const res = await apiClient.post<BuildResponse>("/api/v1/builds", body);
      navigate(`/production/builds/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response?.data
        ?.detail;
      setSubmitError(typeof detail === "string" ? detail : "Could not create build.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">New build</h1>
        </header>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Build details</h2>

          <label className="block text-sm">
            Product
            <EntityPicker
              kind="product"
              value={product}
              onChange={setProduct}
              data-testid="build-product-picker"
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              Assembled from the product&apos;s parts + supplies.
            </span>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Quantity to build
              <Input
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                data-testid="build-qty-input"
              />
            </label>
            <label className="block text-sm">
              Assembly labor (min)
              <Input
                type="number"
                min={0}
                placeholder="from product"
                value={assemblyMinutes}
                onChange={(e) => setAssemblyMinutes(e.target.value)}
                data-testid="build-minutes-input"
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
              data-testid="build-notes-input"
            />
          </label>
        </div>

        {submitError ? (
          <p role="alert" data-testid="build-error" className="text-sm text-destructive">
            {submitError}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button
            type="button"
            disabled={submitting}
            onClick={() => void submit()}
            data-testid="create-build-btn"
          >
            {submitting ? "Saving…" : "Create draft"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={submitting}
            onClick={() => navigate("/production/builds")}
          >
            Cancel
          </Button>
        </div>
      </div>

      <BuildPlanPanel plan={plan} loading={planLoading} error={planError} />
    </section>
  );
}
