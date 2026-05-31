/**
 * `/production/cost-calculator` — standalone cost / price calculator.
 *
 * A "what-if" surface that reuses the exact same cost engine as the job
 * composer's Live cost panel: it posts plate inputs to
 * `POST /api/v1/jobs/calculate` (the `inputs` proposal path, no saved job
 * required) and renders the result with the shared `LiveCostPanel`.
 *
 * Unlike the composer, nothing is persisted — there's no product,
 * customer, or save action. Operators (and sales) can sketch a quantity +
 * plates and read off cost/piece and suggested price without creating a
 * job. Calculation is debounced to 300ms on any meaningful change, matching
 * the composer's UX.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { LiveCostPanel } from "@/components/production/LiveCostPanel";
import {
  EntityPicker,
  type EntityOption,
} from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type CalcResult = components["schemas"]["CalcResultResponse"];
type CalcInputs = components["schemas"]["CalcInputsPayload"];
type CalcPlateInput = components["schemas"]["CalcPlateInputPayload"];
type PrinterResponse = components["schemas"]["PrinterResponse"];

const CALC_DEBOUNCE_MS = 300;

interface MaterialUsageDraft {
  key: string;
  material: EntityOption | null;
  grams: string;
}

interface PlateDraft {
  key: string;
  name: string;
  partsPerSet: string;
  printMinutes: string;
  setupMinutes: string;
  materials: MaterialUsageDraft[];
  printerIds: string[];
}

let _key = 0;
const nextKey = () => `k${++_key}`;

function emptyMaterial(): MaterialUsageDraft {
  return { key: nextKey(), material: null, grams: "" };
}

function emptyPlate(): PlateDraft {
  return {
    key: nextKey(),
    name: "",
    partsPerSet: "1",
    printMinutes: "",
    setupMinutes: "0",
    materials: [emptyMaterial()],
    printerIds: [],
  };
}

function parseIntSafe(s: string, fallback = 0): number {
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : fallback;
}

/** Convert a plate draft to the calc payload, or null when it lacks the
 * minimum inputs (print time + parts/set) the engine needs. Mirrors the
 * job composer so the two surfaces agree byte-for-byte on what's sent. */
function plateToCalcPayload(p: PlateDraft): CalcPlateInput | null {
  const printMinutes = parseIntSafe(p.printMinutes, 0);
  const partsPerSet = parseIntSafe(p.partsPerSet, 0);
  if (printMinutes <= 0 || partsPerSet <= 0) return null;
  const grams: Record<string, number> = {};
  for (const m of p.materials) {
    if (!m.material) continue;
    const g = Number.parseFloat(m.grams);
    if (!Number.isFinite(g) || g <= 0) continue;
    grams[m.material.id] = g;
  }
  return {
    parts_per_set: partsPerSet,
    print_minutes: printMinutes,
    setup_minutes: parseIntSafe(p.setupMinutes, 0),
    print_grams_by_material: grams,
    assigned_printer_ids: p.printerIds,
  };
}

export function CostCalculatorPage() {
  const [quantityOrdered, setQuantityOrdered] = useState("1");
  const [plates, setPlates] = useState<PlateDraft[]>(() => [emptyPlate()]);
  const [printers, setPrinters] = useState<PrinterResponse[]>([]);

  const [calcResult, setCalcResult] = useState<CalcResult | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);

  // Fetch printers once for the assignment selectors. Per-printer cost
  // params feed the machine-cost path; without an assignment the engine
  // falls back to the flat machine rate.
  useEffect(() => {
    let cancelled = false;
    api
      .get("/api/v1/printers", { params: { is_archived: "false" } })
      .then((res) => {
        if (!cancelled) setPrinters(res.data.items);
      })
      .catch(() => {
        /* non-fatal — printers may be unconfigured */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const calcInputs = useMemo<CalcInputs | null>(() => {
    const qty = parseIntSafe(quantityOrdered, 0);
    if (qty <= 0) return null;
    const plateInputs = plates
      .map(plateToCalcPayload)
      .filter((p): p is NonNullable<typeof p> => p !== null);
    if (plateInputs.length === 0) return null;
    return { quantity_ordered: qty, plates: plateInputs };
  }, [plates, quantityOrdered]);

  // Watch a stable JSON hash so identical payloads don't re-trigger.
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
          if (id !== lastRequestId.current) return;
          setCalcResult(res.data);
        })
        .catch((err: unknown) => {
          if (id !== lastRequestId.current) return;
          const detail = (err as { response?: { data?: { detail?: string } } })
            .response?.data?.detail;
          setCalcError(
            typeof detail === "string" ? detail : "Could not calculate cost.",
          );
        })
        .finally(() => {
          if (id === lastRequestId.current) setCalcLoading(false);
        });
    }, CALC_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
    // calcHash captures every meaningful input change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calcHash]);

  function updatePlate(idx: number, patch: Partial<PlateDraft>) {
    setPlates((prev) =>
      prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)),
    );
  }

  function updateMaterial(
    plateIdx: number,
    matIdx: number,
    patch: Partial<MaterialUsageDraft>,
  ) {
    setPlates((prev) =>
      prev.map((p, i) => {
        if (i !== plateIdx) return p;
        const mats = p.materials.map((m, j) =>
          j === matIdx ? { ...m, ...patch } : m,
        );
        return { ...p, materials: mats };
      }),
    );
  }

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header className="space-y-1">
          <h1 className="text-xl font-semibold">Cost / price calculator</h1>
          <p className="text-sm text-muted-foreground">
            Sketch a quantity and plates to estimate cost and suggested price.
            Uses the same cost engine as a job's Live cost — nothing is saved.
          </p>
        </header>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Order</h2>
          <label className="block text-sm">
            Quantity
            <Input
              type="number"
              min={1}
              value={quantityOrdered}
              onChange={(e) => setQuantityOrdered(e.target.value)}
              data-testid="calc-qty-input"
            />
          </label>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Plates</h2>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setPlates((p) => [...p, emptyPlate()])}
              data-testid="calc-add-plate-btn"
            >
              Add plate
            </Button>
          </div>

          {plates.map((plate, idx) => (
            <div
              key={plate.key}
              className="space-y-3 rounded-lg border border-border p-4"
              data-testid={`calc-plate-row-${idx}`}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">Plate {idx + 1}</h3>
                {plates.length > 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setPlates((prev) => prev.filter((_, i) => i !== idx))
                    }
                    data-testid={`calc-remove-plate-${idx}`}
                  >
                    Remove
                  </Button>
                ) : null}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm">
                  Name
                  <Input
                    value={plate.name}
                    onChange={(e) => updatePlate(idx, { name: e.target.value })}
                    data-testid={`calc-plate-name-${idx}`}
                  />
                </label>
                <label className="block text-sm">
                  Parts / set
                  <Input
                    type="number"
                    min={1}
                    value={plate.partsPerSet}
                    onChange={(e) =>
                      updatePlate(idx, { partsPerSet: e.target.value })
                    }
                    data-testid={`calc-plate-parts-${idx}`}
                  />
                </label>
                <label className="block text-sm">
                  Print minutes
                  <Input
                    type="number"
                    min={1}
                    value={plate.printMinutes}
                    onChange={(e) =>
                      updatePlate(idx, { printMinutes: e.target.value })
                    }
                    data-testid={`calc-plate-print-minutes-${idx}`}
                  />
                </label>
                <label className="block text-sm">
                  Setup minutes
                  <Input
                    type="number"
                    min={0}
                    value={plate.setupMinutes}
                    onChange={(e) =>
                      updatePlate(idx, { setupMinutes: e.target.value })
                    }
                    data-testid={`calc-plate-setup-minutes-${idx}`}
                  />
                </label>
              </div>

              <fieldset className="space-y-2">
                <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Filament usage
                </legend>
                {plate.materials.map((m, mIdx) => (
                  <div
                    key={m.key}
                    className="flex items-end gap-2"
                    data-testid={`calc-plate-${idx}-material-${mIdx}`}
                  >
                    <div className="flex-1">
                      <EntityPicker
                        kind="material"
                        value={m.material}
                        onChange={(opt) =>
                          updateMaterial(idx, mIdx, { material: opt })
                        }
                        data-testid={`calc-plate-${idx}-material-picker-${mIdx}`}
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
                        onChange={(e) =>
                          updateMaterial(idx, mIdx, { grams: e.target.value })
                        }
                        data-testid={`calc-plate-${idx}-grams-${mIdx}`}
                      />
                    </label>
                    {plate.materials.length > 1 ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setPlates((prev) =>
                            prev.map((p, i) =>
                              i === idx
                                ? {
                                    ...p,
                                    materials: p.materials.filter(
                                      (_, j) => j !== mIdx,
                                    ),
                                  }
                                : p,
                            ),
                          );
                        }}
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
                    onClick={() =>
                      updatePlate(idx, {
                        materials: [...plate.materials, emptyMaterial()],
                      })
                    }
                    data-testid={`calc-add-material-${idx}`}
                  >
                    + filament
                  </Button>
                  <span data-testid={`calc-plate-${idx}-grams-sum`}>
                    Σ{" "}
                    {plate.materials
                      .reduce((acc, m) => {
                        const g = Number.parseFloat(m.grams);
                        return Number.isFinite(g) ? acc + g : acc;
                      }, 0)
                      .toFixed(1)}{" "}
                    g
                  </span>
                </div>
              </fieldset>

              <fieldset>
                <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Eligible printers
                </legend>
                <div className="mt-1 flex flex-wrap gap-2">
                  {printers.length === 0 ? (
                    <span className="text-xs text-muted-foreground">
                      No printers configured.
                    </span>
                  ) : (
                    printers.map((pr) => {
                      const checked = plate.printerIds.includes(pr.id);
                      return (
                        <label
                          key={pr.id}
                          className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-input px-2 py-1 text-xs"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              const next = checked
                                ? plate.printerIds.filter((id) => id !== pr.id)
                                : [...plate.printerIds, pr.id];
                              updatePlate(idx, { printerIds: next });
                            }}
                            data-testid={`calc-plate-${idx}-printer-${pr.id}`}
                          />
                          {pr.name}
                        </label>
                      );
                    })
                  )}
                </div>
              </fieldset>
            </div>
          ))}
        </div>
      </div>

      <LiveCostPanel
        result={calcResult}
        loading={calcLoading}
        error={calcError}
      />
    </section>
  );
}
