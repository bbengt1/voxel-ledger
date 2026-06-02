/**
 * `/catalog/parts/new` — create a Part (assembly-line epic #267, Phase 1b).
 * Identity + print recipe (minutes, setup, parts/run, filament usage,
 * eligible printers) with a live cost panel that recomputes from the
 * recipe as you fill it in.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { EntityPicker, type EntityOption } from "@/components/inventory/EntityPicker";
import { DiscoveryUpload } from "@/components/production/DiscoveryUpload";
import { LiveCostPanel } from "@/components/production/LiveCostPanel";
import {
  PrinterFileBrowser,
  type PrinterSource,
} from "@/components/production/PrinterFileBrowser";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type PartResponse = components["schemas"]["PartResponse"];
type PrinterResponse = components["schemas"]["PrinterResponse"];
type DiscoveredPlate = components["schemas"]["DiscoveredPlateResponse"];
type CalcResult = components["schemas"]["CalcResultResponse"];
type CalcInputs = components["schemas"]["CalcInputsPayload"];

const CALC_DEBOUNCE_MS = 300;

interface MaterialRow {
  key: string;
  material: EntityOption | null;
  grams: string;
  /** Slicer slot/label this row was imported from (operator maps it to a material). */
  slotLabel?: string;
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
  const [calcResult, setCalcResult] = useState<CalcResult | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [importedFrom, setImportedFrom] = useState<string | null>(null);
  const [printerBrowserOpen, setPrinterBrowserOpen] = useState(false);
  // When the recipe came from a printer, remember which file so we can
  // attach its embedded thumbnail as the part image after create.
  const [printerSource, setPrinterSource] = useState<PrinterSource | null>(null);
  // When an uploaded artifact carried an embedded thumbnail (base64 PNG),
  // remember it to attach as the part image after create.
  const [uploadThumbnail, setUploadThumbnail] = useState<string | null>(null);

  function handleDiscovered(plate: DiscoveredPlate, source?: PrinterSource) {
    // Carry over the pre-v2 gcode discovery (epic #267): pre-fill the
    // recipe from the slicer artifact. The parser keys filament by slicer
    // slot/label, not by material id — so we seed a row per filament with
    // grams filled in and leave the material picker for the operator.
    setPrintMinutes(String(plate.print_minutes));
    setPartsPerRun(String(plate.parts_per_set ?? 1));
    const entries = Object.entries(plate.filament_grams_by_material ?? {});
    if (entries.length > 0) {
      setMaterials(
        entries.map(([slot, grams]) => ({
          key: nextKey(),
          material: null,
          grams: String(grams),
          slotLabel: slot,
        })),
      );
    }
    setImportedFrom(plate.source_filename ?? plate.source_format ?? "slicer file");
    setPrinterSource(source ?? null);
    // File-upload path may carry an embedded thumbnail; the printer path
    // attaches its image separately (via printerSource).
    setUploadThumbnail(source ? null : (plate.thumbnail_b64 ?? null));
    setError(null);
  }

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

  // Live cost from the recipe — costed as a single plate of `parts_per_run`
  // pieces, so `cost_per_piece` is the per-part cost (same basis as the
  // saved part's /cost). Filament only counts once a material is picked.
  const calcInputs = useMemo<CalcInputs | null>(() => {
    const pps = parseIntSafe(partsPerRun, 0);
    if (pps <= 0) return null;
    const grams: Record<string, number> = {};
    for (const m of materials) {
      if (!m.material) continue;
      const g = Number.parseFloat(m.grams);
      if (Number.isFinite(g) && g > 0) grams[m.material.id] = g;
    }
    return {
      quantity_ordered: pps,
      plates: [
        {
          parts_per_set: pps,
          print_minutes: parseIntSafe(printMinutes, 0),
          setup_minutes: parseIntSafe(setupMinutes, 0),
          print_grams_by_material: grams,
          assigned_printer_ids: printerIds,
        },
      ],
    };
  }, [partsPerRun, printMinutes, setupMinutes, materials, printerIds]);

  const calcHash = useMemo(
    () => (calcInputs ? JSON.stringify(calcInputs) : ""),
    [calcInputs],
  );
  const lastCalcId = useRef(0);

  useEffect(() => {
    if (!calcInputs) {
      setCalcResult(null);
      setCalcError(null);
      setCalcLoading(false);
      return;
    }
    const handle = window.setTimeout(() => {
      const id = ++lastCalcId.current;
      setCalcLoading(true);
      setCalcError(null);
      apiClient
        .post<CalcResult>("/api/v1/jobs/calculate", { inputs: calcInputs })
        .then((res) => {
          if (id === lastCalcId.current) setCalcResult(res.data);
        })
        .catch((err: unknown) => {
          if (id !== lastCalcId.current) return;
          const detail = (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail;
          setCalcError(typeof detail === "string" ? detail : "Could not calculate cost.");
        })
        .finally(() => {
          if (id === lastCalcId.current) setCalcLoading(false);
        });
    }, CALC_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calcHash]);

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
      // If the recipe came from a printer, attach that gcode's embedded
      // thumbnail as the part image (best-effort — never block the create).
      if (printerSource) {
        try {
          await apiClient.post(`/api/v1/parts/${res.data.id}/image/from-printer`, {
            printer_id: printerSource.printerId,
            filename: printerSource.filename,
          });
        } catch {
          /* no embedded thumbnail or fetch failed — the part is still created */
        }
      } else if (uploadThumbnail) {
        // The uploaded artifact carried an embedded preview — attach it as
        // the part image (best-effort).
        try {
          const bytes = Uint8Array.from(atob(uploadThumbnail), (c) => c.charCodeAt(0));
          const form = new FormData();
          form.append("file", new File([bytes], "thumbnail.png", { type: "image/png" }));
          await apiClient.post(`/api/v1/parts/${res.data.id}/image`, form, {
            headers: { "Content-Type": "multipart/form-data" },
          });
        } catch {
          /* image is a nice-to-have — never block the create */
        }
      }
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
    <section className="flex gap-6">
      <div className="flex-1">
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

          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              Import a sliced <code>.gcode.json</code> / <code>.3mf</code>, or look one up on a
              printer, to auto-fill the recipe.
            </span>
            <div className="flex items-center gap-2">
              <DiscoveryUpload
                endpoint="/api/v1/parts/discover"
                onDiscovered={handleDiscovered}
                data-testid="part-discovery"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setPrinterBrowserOpen(true)}
                data-testid="part-discovery-printer"
              >
                Look up on printer
              </Button>
            </div>
          </div>
          {importedFrom ? (
            <p
              role="status"
              data-testid="part-discovery-imported"
              className="rounded bg-muted/40 px-2 py-1 text-xs text-muted-foreground"
            >
              Imported <span className="font-medium text-foreground">{importedFrom}</span> — match
              each imported filament to a material below.
              {printerSource || uploadThumbnail
                ? " Its embedded thumbnail will be attached as the part image."
                : ""}
            </p>
          ) : null}

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
                  {m.slotLabel && !m.material ? (
                    <span className="mb-0.5 block text-[10px] text-muted-foreground">
                      from <span className="font-mono">{m.slotLabel}</span> — pick a material
                    </span>
                  ) : null}
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

      <PrinterFileBrowser
        open={printerBrowserOpen}
        onClose={() => setPrinterBrowserOpen(false)}
        onPicked={handleDiscovered}
        discoverEndpoint="/api/v1/parts/discover-from-printer"
      />
      </div>

      <LiveCostPanel result={calcResult} loading={calcLoading} error={calcError} />
    </section>
  );
}
