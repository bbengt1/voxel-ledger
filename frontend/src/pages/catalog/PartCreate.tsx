/**
 * `/catalog/parts/new` — create a Part (assembly-line epic #267, Phase 1b).
 * Identity + print recipe (minutes, setup, parts/run, filament usage,
 * eligible printers). Cost is computed later (Phase 2).
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { EntityPicker, type EntityOption } from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type PartResponse = components["schemas"]["PartResponse"];
type PrinterResponse = components["schemas"]["PrinterResponse"];

interface MaterialRow {
  key: string;
  material: EntityOption | null;
  grams: string;
}

let _key = 0;
const nextKey = () => `m${++_key}`;
const emptyRow = (): MaterialRow => ({ key: nextKey(), material: null, grams: "" });

function parseIntSafe(s: string, fallback = 0): number {
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : fallback;
}

export function PartCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [description, setDescription] = useState("");
  const [printMinutes, setPrintMinutes] = useState("");
  const [setupMinutes, setSetupMinutes] = useState("0");
  const [partsPerRun, setPartsPerRun] = useState("1");
  const [materials, setMaterials] = useState<MaterialRow[]>(() => [emptyRow()]);
  const [printers, setPrinters] = useState<PrinterResponse[]>([]);
  const [printerIds, setPrinterIds] = useState<string[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get("/api/v1/printers", { params: { is_archived: "false" } })
      .then((res) => {
        if (!cancelled) setPrinters(res.data.items);
      })
      .catch(() => {
        /* non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const gramsSum = useMemo(
    () =>
      materials.reduce((acc, m) => {
        const g = Number.parseFloat(m.grams);
        return Number.isFinite(g) ? acc + g : acc;
      }, 0),
    [materials],
  );

  function updateRow(key: string, patch: Partial<MaterialRow>) {
    setMaterials((prev) => prev.map((m) => (m.key === key ? { ...m, ...patch } : m)));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const partsPerRunNum = parseIntSafe(partsPerRun, 0);
      if (partsPerRunNum <= 0) {
        setError("Parts per run must be at least 1.");
        setSubmitting(false);
        return;
      }
      const grams: Record<string, string> = {};
      for (const m of materials) {
        if (!m.material) continue;
        const g = Number.parseFloat(m.grams);
        if (!Number.isFinite(g) || g <= 0) continue;
        grams[m.material.id] = String(g);
      }
      const body: Record<string, unknown> = {
        name,
        print_minutes: parseIntSafe(printMinutes, 0),
        setup_minutes: parseIntSafe(setupMinutes, 0),
        parts_per_run: partsPerRunNum,
        print_grams_by_material: grams,
        assigned_printer_ids: printerIds,
      };
      if (sku.trim()) body["sku"] = sku.trim();
      if (description.trim()) body["description"] = description.trim();
      const res = await apiClient.post<PartResponse>("/api/v1/parts", body);
      navigate(`/catalog/parts/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        "Could not create part.";
      setError(typeof detail === "string" ? detail : "Could not create part.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New part</h1>
      <form className="mt-6 space-y-3" onSubmit={onSubmit}>
        <label className="block text-sm">
          Name
          <Input className="mt-1" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="block text-sm">
          SKU
          <Input
            className="mt-1"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder="auto-generated"
            data-testid="part-sku-input"
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Leave blank to auto-generate as PART-YYYY-NNNN.
          </span>
        </label>
        <label className="block text-sm">
          Description
          <Input
            className="mt-1"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>

        <fieldset className="space-y-3 rounded border border-border p-3">
          <legend className="px-1 text-xs uppercase text-muted-foreground">Print recipe</legend>
          <div className="grid grid-cols-3 gap-3">
            <label className="block text-sm">
              Print min
              <Input
                type="number"
                min={0}
                className="mt-1"
                value={printMinutes}
                onChange={(e) => setPrintMinutes(e.target.value)}
                data-testid="part-print-minutes"
              />
            </label>
            <label className="block text-sm">
              Setup min
              <Input
                type="number"
                min={0}
                className="mt-1"
                value={setupMinutes}
                onChange={(e) => setSetupMinutes(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              Parts/run
              <Input
                type="number"
                min={1}
                className="mt-1"
                value={partsPerRun}
                onChange={(e) => setPartsPerRun(e.target.value)}
                data-testid="part-parts-per-run"
              />
            </label>
          </div>

          <div className="space-y-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Filament usage
            </span>
            {materials.map((m, idx) => (
              <div key={m.key} className="flex items-end gap-2" data-testid={`part-material-${idx}`}>
                <div className="flex-1">
                  <EntityPicker
                    kind="material"
                    value={m.material}
                    onChange={(opt) => updateRow(m.key, { material: opt })}
                  />
                </div>
                <label className="block text-xs">
                  Grams
                  <Input
                    type="number"
                    min={0}
                    step="0.1"
                    className="w-24"
                    value={m.grams}
                    onChange={(e) => updateRow(m.key, { grams: e.target.value })}
                  />
                </label>
                {materials.length > 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => setMaterials((prev) => prev.filter((r) => r.key !== m.key))}
                  >
                    ×
                  </Button>
                ) : null}
              </div>
            ))}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setMaterials((prev) => [...prev, emptyRow()])}
              >
                + filament
              </Button>
              <span>Σ {gramsSum.toFixed(1)} g</span>
            </div>
          </div>

          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Eligible printers
            </span>
            <div className="mt-1 flex flex-wrap gap-2">
              {printers.length === 0 ? (
                <span className="text-xs text-muted-foreground">No printers configured.</span>
              ) : (
                printers.map((pr) => {
                  const checked = printerIds.includes(pr.id);
                  return (
                    <label
                      key={pr.id}
                      className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-input px-2 py-1 text-xs"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          setPrinterIds((prev) =>
                            checked ? prev.filter((id) => id !== pr.id) : [...prev, pr.id],
                          )
                        }
                      />
                      {pr.name}
                    </label>
                  );
                })
              )}
            </div>
          </div>
        </fieldset>

        {error ? (
          <p role="alert" data-testid="create-error" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create part"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/catalog/parts")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
