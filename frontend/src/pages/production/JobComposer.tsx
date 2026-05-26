/**
 * `/production/jobs/new` — job composer with live cost panel.
 *
 * Layout: header form on the left, sticky cost panel on the right. Each
 * plate row owns its own filament rows and printer-assignment multi-select.
 * Cost calculation is debounced to 300ms on any meaningful change
 * (per UX spec / Doherty threshold). A spinner is shown during in-flight
 * calculate requests.
 *
 * The composer intentionally posts a single `JobCreate` payload that
 * includes plates inline — that matches the v2 backend contract and
 * keeps the UX as a single "save" action.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { DiscoveryUpload } from "@/components/production/DiscoveryUpload";
import { PrinterFileBrowser } from "@/components/production/PrinterFileBrowser";
import { LiveCostPanel } from "@/components/production/LiveCostPanel";
import {
  EntityPicker,
  type EntityOption,
} from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  clearJobComposerDraft,
  loadJobComposerDraft,
  saveJobComposerDraft,
} from "@/lib/jobComposerDraft";

type CalcResult = components["schemas"]["CalcResultResponse"];
type CalcInputs = components["schemas"]["CalcInputsPayload"];
type DiscoveredPlate = components["schemas"]["DiscoveredPlateResponse"];
type JobResponse = components["schemas"]["JobResponse"];
type PrinterResponse = components["schemas"]["PrinterResponse"];
type MaterialResponse = components["schemas"]["MaterialResponse"];

const CALC_DEBOUNCE_MS = 300;

interface MaterialUsageDraft {
  /** stable key for React lists */
  key: string;
  material: EntityOption | null;
  grams: string;
  /** Slot name from gcode discovery — used as a hint and to pre-fill
   * MaterialCreate when the operator clicks "Create material". */
  discoveredName?: string;
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

/** Strip slicer-generated artifacts from an imported filename so we can
 * propose it as a product name. Removes file extensions (``.gcode``,
 * ``.gcode.json``, ``.3mf``), trailing time tags (``_6h44m``), filament
 * tags (``_PLA``, ``_PETG``), and version suffixes (``_v6``). Whitespace
 * is collapsed so what's left reads cleanly in the picker. */
function cleanProductNameFromFilename(raw: string | null | undefined): string {
  if (!raw) return "";
  let s = raw.trim();
  // Drop any path component the source had.
  if (s.includes("/")) s = s.substring(s.lastIndexOf("/") + 1);
  // Strip well-known extensions, including compound .gcode.json.
  s = s.replace(/\.(gcode\.json|gcode|3mf|json)$/i, "");
  // Drop print-time suffixes like ``_6h44m`` or ``_12m30s``.
  s = s.replace(/[_-]\d+h\d+m(\d+s)?$/i, "");
  s = s.replace(/[_-]\d+m\d+s?$/i, "");
  // Filament hint and version suffixes.
  s = s.replace(/[_-](pla\+?|petg|abs|asa|tpu|tpe|nylon|pc|pva|hips)$/i, "");
  s = s.replace(/[_-]v\d+$/i, "");
  // Collapse remaining separators to spaces for readability.
  return s.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}


function parseIntSafe(s: string, fallback = 0): number {
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : fallback;
}

function plateToCalcPayload(p: PlateDraft):
  | components["schemas"]["CalcPlateInputPayload"]
  | null {
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

export function JobComposerPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [product, setProduct] = useState<EntityOption | null>(null);
  const [customer, setCustomer] = useState("");
  const [quantityOrdered, setQuantityOrdered] = useState("1");
  const [priority, setPriority] = useState("0");
  const [dueAt, setDueAt] = useState("");
  const [notes, setNotes] = useState("");
  const [plates, setPlates] = useState<PlateDraft[]>(() => [emptyPlate()]);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [browsingPlateIdx, setBrowsingPlateIdx] = useState<number | null>(null);
  // Confirm-before-write prompt for the Product field after an import.
  // ``suggested`` is the cleaned product name pulled from the file;
  // ``current`` is the label that's already set (so the operator can
  // see what they'd be replacing).
  const [productPrompt, setProductPrompt] = useState<{
    suggested: string;
    current: string | null;
  } | null>(null);

  const [printers, setPrinters] = useState<PrinterResponse[]>([]);
  const [materialsById, setMaterialsById] = useState<
    Record<string, MaterialResponse>
  >({});

  // Cost panel state — owned here so we can show a single spinner across
  // plates.
  const [calcResult, setCalcResult] = useState<CalcResult | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);

  // Fetch printers once for the assignment selectors.
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

  // Build calc inputs payload — null if not enough data to bother.
  const calcInputs = useMemo<CalcInputs | null>(() => {
    const qty = parseIntSafe(quantityOrdered, 0);
    if (qty <= 0) return null;
    const plateInputs = plates
      .map(plateToCalcPayload)
      .filter((p): p is NonNullable<typeof p> => p !== null);
    if (plateInputs.length === 0) return null;
    return { quantity_ordered: qty, plates: plateInputs };
  }, [plates, quantityOrdered]);

  // Debounced calculate call. We watch a JSON-stringified hash so the
  // dependency comparison is stable across new identical payloads.
  const calcHash = useMemo(
    () => (calcInputs ? JSON.stringify(calcInputs) : ""),
    [calcInputs],
  );

  // Track the in-flight request so a newer one can short-circuit the old.
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

  /** Snapshot the full composer to sessionStorage and route to the
   * material-create page with the discovered slot name + a return
   * marker. On successful create that page navigates back to
   * ``/production/jobs/new?restored=1&plate=<idx>&slot=<key>&material_id=<id>``
   * and the effect below splices the new material into this slot.
   */
  function createMaterialForSlot(plateIdx: number, mat: MaterialUsageDraft) {
    saveJobComposerDraft({
      customer,
      quantityOrdered,
      priority,
      dueAt,
      notes,
      product,
      plates,
      pending: { plateIdx, slotKey: mat.key },
    });
    const guessedName = mat.discoveredName ?? "";
    const guessedType = guessedName.toUpperCase().includes("PETG")
      ? "PETG"
      : guessedName.toUpperCase().includes("ABS")
        ? "ABS"
        : guessedName.toUpperCase().includes("TPU")
          ? "TPU"
          : "PLA";
    const params = new URLSearchParams();
    if (guessedName) params.set("name", guessedName);
    params.set("material_type", guessedType);
    params.set("return_to", "job_composer");
    navigate(`/catalog/materials/new?${params.toString()}`);
  }

  /** Same round-trip pattern as ``createMaterialForSlot`` but for the
   * product picker. No pending-slot marker is needed — the restore
   * effect just sees ``product_id`` in the URL and applies it. */
  function createProductFromComposer() {
    saveJobComposerDraft({
      customer,
      quantityOrdered,
      priority,
      dueAt,
      notes,
      product,
      plates,
      pending: null,
    });
    const params = new URLSearchParams();
    params.set("return_to", "job_composer");
    navigate(`/catalog/products/new?${params.toString()}`);
  }

  function applyDiscovered(plateIdx: number, disc: DiscoveredPlate) {
    setPlates((prev) =>
      prev.map((p, i) => {
        if (i !== plateIdx) return p;
        // Best-effort match: discovery returns material name keys; we map
        // them to the materials catalog when we can. Anything unmatched is
        // left as a placeholder grams entry the user must wire up.
        const mats: MaterialUsageDraft[] = [];
        const grams = disc.filament_grams_by_material ?? {};
        for (const [name, g] of Object.entries(grams)) {
          const needle = name.toLowerCase();
          const catalog = Object.values(materialsById);
          // Exact case-insensitive match wins; fall back to substring
          // either direction so "Generic PLA Silk" finds a catalog
          // entry called "PLA Silk" (and vice versa).
          const found =
            catalog.find((m) => m.name.toLowerCase() === needle) ||
            catalog.find(
              (m) =>
                needle.includes(m.name.toLowerCase()) ||
                m.name.toLowerCase().includes(needle),
            );
          mats.push({
            key: nextKey(),
            material: found ? { id: found.id, label: found.name } : null,
            grams: g,
            discoveredName: name,
          });
        }
        return {
          ...p,
          name: p.name || disc.source_filename || `Plate ${plateIdx + 1}`,
          partsPerSet: String(disc.parts_per_set),
          printMinutes: String(disc.print_minutes),
          materials: mats.length > 0 ? mats : p.materials,
        };
      }),
    );
    // After a plate is populated, propose the cleaned filename as the
    // Product name — but never write it without explicit confirmation.
    // Skip when we have nothing useful or the suggestion already matches
    // the currently-selected product.
    const suggested = cleanProductNameFromFilename(disc.source_filename);
    if (suggested && suggested.toLowerCase() !== (product?.label ?? "").toLowerCase()) {
      setProductPrompt({ suggested, current: product?.label ?? null });
    }
  }

  /** Confirm path for the import-suggested product. Tries to find a
   * catalog product whose name matches the suggestion (exact, then
   * substring); on miss, kicks off the existing create-product round
   * trip with the name pre-filled. */
  async function acceptProductSuggestion() {
    if (!productPrompt) return;
    const needle = productPrompt.suggested.toLowerCase();
    try {
      const res = await api.get("/api/v1/products", {
        params: { search: productPrompt.suggested, is_archived: "false" },
      });
      const items = res.data.items;
      const exact = items.find((p) => p.name.toLowerCase() === needle);
      const fuzzy =
        exact ||
        items.find(
          (p) =>
            needle.includes(p.name.toLowerCase()) ||
            p.name.toLowerCase().includes(needle),
        );
      if (fuzzy) {
        setProduct({ id: fuzzy.id, label: fuzzy.name });
        setProductPrompt(null);
        return;
      }
    } catch {
      /* fall through to create */
    }
    // No catalog hit — round-trip to the create-product page with the
    // name pre-filled. The existing createProductFromComposer flow
    // restores composer state on return.
    saveJobComposerDraft({
      customer,
      quantityOrdered,
      priority,
      dueAt,
      notes,
      product,
      plates,
      pending: null,
    });
    const params = new URLSearchParams();
    params.set("name", productPrompt.suggested);
    params.set("return_to", "job_composer");
    setProductPrompt(null);
    navigate(`/catalog/products/new?${params.toString()}`);
  }

  /** Restore in-progress composer state after a side-trip to
   * /catalog/materials/new. The material-create page navigates here
   * with ``?restored=1&material_id=…`` after a successful save; we
   * hydrate from sessionStorage and slot the new material into the
   * row the user was filling out. Runs once. */
  useEffect(() => {
    if (searchParams.get("restored") !== "1") return;
    const draft = loadJobComposerDraft();
    if (!draft) {
      // Lost the snapshot somehow — strip the query and proceed empty.
      setSearchParams({}, { replace: true });
      return;
    }
    setCustomer(draft.customer);
    setQuantityOrdered(draft.quantityOrdered);
    setPriority(draft.priority);
    setDueAt(draft.dueAt);
    setNotes(draft.notes);
    setProduct(draft.product);
    setPlates(draft.plates as PlateDraft[]);

    // Newly-created product (from /catalog/products/new) — replaces the
    // ``product`` we restored from the draft.
    const newProductId = searchParams.get("product_id");
    const newProductLabel = searchParams.get("product_label") ?? "";
    if (newProductId) {
      setProduct({
        id: newProductId,
        label: newProductLabel || "Product",
      });
    }

    const newMaterialId = searchParams.get("material_id");
    const newMaterialLabel = searchParams.get("material_label") ?? "";
    const pending = draft.pending;
    if (newMaterialId && pending) {
      setPlates((prev) =>
        prev.map((p, i) =>
          i !== pending.plateIdx
            ? p
            : {
                ...p,
                materials: p.materials.map((m) =>
                  m.key !== pending.slotKey
                    ? m
                    : {
                        ...m,
                        material: {
                          id: newMaterialId,
                          label: newMaterialLabel || m.discoveredName || "Material",
                        },
                      },
                ),
              },
        ),
      );
    }
    clearJobComposerDraft();
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Eagerly fetch known materials so discovery matching works.
  useEffect(() => {
    let cancelled = false;
    api
      .get("/api/v1/materials", { params: { is_archived: "false" } })
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, MaterialResponse> = {};
        for (const m of res.data.items) map[m.id] = m;
        setMaterialsById(map);
      })
      .catch(() => {
        /* non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = useCallback(
    async (alsoSubmitToQueue: boolean) => {
      if (!product) {
        setSubmitError("Pick a product first.");
        return;
      }
      const qty = parseIntSafe(quantityOrdered, 0);
      if (qty <= 0) {
        setSubmitError("Quantity must be at least 1.");
        return;
      }
      const platePayload: components["schemas"]["PlateCreate"][] = [];
      for (let i = 0; i < plates.length; i++) {
        const p = plates[i]!;
        const printMinutes = parseIntSafe(p.printMinutes, 0);
        const partsPerSet = parseIntSafe(p.partsPerSet, 0);
        if (printMinutes <= 0 || partsPerSet <= 0) {
          setSubmitError(
            `Plate ${i + 1}: print minutes and parts/set are required.`,
          );
          return;
        }
        const grams: Record<string, number> = {};
        for (const m of p.materials) {
          if (!m.material) continue;
          const g = Number.parseFloat(m.grams);
          if (!Number.isFinite(g) || g <= 0) continue;
          grams[m.material.id] = g;
        }
        platePayload.push({
          name: p.name || `Plate ${i + 1}`,
          plate_number: i + 1,
          parts_per_set: partsPerSet,
          print_minutes: printMinutes,
          print_hours_setup_minutes: parseIntSafe(p.setupMinutes, 0),
          print_grams_by_material: grams,
          assigned_printer_ids: p.printerIds,
        });
      }

      setSubmitting(true);
      setSubmitError(null);
      try {
        const body: components["schemas"]["JobCreate"] = {
          product_id: product.id,
          quantity_ordered: qty,
          priority: parseIntSafe(priority, 0),
          plates: platePayload,
        };
        if (dueAt) body.due_at = new Date(dueAt).toISOString();
        const trimmedNotes = (
          notes + (customer ? `\n\nCustomer: ${customer}` : "")
        ).trim();
        if (trimmedNotes) body.notes = trimmedNotes;

        const res = await apiClient.post<JobResponse>(
          "/api/v1/jobs",
          body,
        );
        if (alsoSubmitToQueue) {
          await apiClient.post(`/api/v1/jobs/${res.data.id}/submit`);
        }
        navigate(`/production/jobs/${res.data.id}`);
      } catch (err: unknown) {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setSubmitError(
          typeof detail === "string" ? detail : "Could not save job.",
        );
      } finally {
        setSubmitting(false);
      }
    },
    [
      customer,
      dueAt,
      navigate,
      notes,
      plates,
      priority,
      product,
      quantityOrdered,
    ],
  );

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">New job</h1>
        </header>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Job details</h2>

          {productPrompt ? (
            <div
              role="status"
              className="flex flex-wrap items-center justify-between gap-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950/40"
              data-testid="product-import-prompt"
            >
              <div className="min-w-0">
                <p className="font-medium">
                  {productPrompt.current
                    ? `Replace product "${productPrompt.current}" with "${productPrompt.suggested}"?`
                    : `Use "${productPrompt.suggested}" as the Product?`}
                </p>
                <p className="text-xs text-muted-foreground">
                  Pulled from the imported file. Existing catalog entries will
                  be linked; otherwise we'll create a new product.
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void acceptProductSuggestion()}
                  data-testid="product-import-accept"
                >
                  {productPrompt.current ? "Replace" : "Use"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setProductPrompt(null)}
                  data-testid="product-import-skip"
                >
                  Skip
                </Button>
              </div>
            </div>
          ) : null}

          <label className="block text-sm">
            Product
            <EntityPicker
              kind="product"
              value={product}
              onChange={setProduct}
              data-testid="job-product-picker"
            />
            {!product ? (
              <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>No matching product? Create one and come back.</span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={createProductFromComposer}
                  data-testid="job-create-product"
                >
                  Create product
                </Button>
              </div>
            ) : null}
          </label>
          <label className="block text-sm">
            Customer (free text)
            <Input
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
              data-testid="job-customer-input"
            />
          </label>
          <div className="grid grid-cols-3 gap-3">
            <label className="block text-sm">
              Quantity ordered
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

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Plates</h2>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setPlates((p) => [...p, emptyPlate()])}
              data-testid="add-plate-btn"
            >
              Add plate
            </Button>
          </div>

          {plates.map((plate, idx) => (
            <div
              key={plate.key}
              className="space-y-3 rounded-lg border border-border p-4"
              data-testid={`plate-row-${idx}`}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">Plate {idx + 1}</h3>
                <div className="flex items-center gap-2">
                  <DiscoveryUpload
                    onDiscovered={(d) => applyDiscovered(idx, d)}
                    data-testid={`discover-plate-${idx}`}
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => setBrowsingPlateIdx(idx)}
                    data-testid={`browse-printer-plate-${idx}`}
                  >
                    Browse printer files
                  </Button>
                  {plates.length > 1 ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        setPlates((prev) => prev.filter((_, i) => i !== idx))
                      }
                      data-testid={`remove-plate-${idx}`}
                    >
                      Remove
                    </Button>
                  ) : null}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="block text-sm">
                  Name
                  <Input
                    value={plate.name}
                    onChange={(e) => updatePlate(idx, { name: e.target.value })}
                    data-testid={`plate-name-${idx}`}
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
                    data-testid={`plate-parts-${idx}`}
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
                    data-testid={`plate-print-minutes-${idx}`}
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
                    data-testid={`plate-setup-minutes-${idx}`}
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
                    data-testid={`plate-${idx}-material-${mIdx}`}
                  >
                    <div className="flex-1 space-y-1">
                      <EntityPicker
                        kind="material"
                        value={m.material}
                        onChange={(opt) =>
                          updateMaterial(idx, mIdx, { material: opt })
                        }
                        data-testid={`plate-${idx}-material-picker-${mIdx}`}
                      />
                      {m.discoveredName && !m.material ? (
                        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                          <span title={m.discoveredName} className="truncate">
                            Discovered: <span className="font-medium">{m.discoveredName}</span> — no catalog match
                          </span>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => createMaterialForSlot(idx, m)}
                            data-testid={`plate-${idx}-create-material-${mIdx}`}
                          >
                            Create material
                          </Button>
                        </div>
                      ) : null}
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
                        data-testid={`plate-${idx}-grams-${mIdx}`}
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
                    data-testid={`add-material-${idx}`}
                  >
                    + filament
                  </Button>
                  <span data-testid={`plate-${idx}-grams-sum`}>
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
                            data-testid={`plate-${idx}-printer-${pr.id}`}
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

        {submitError ? (
          <p
            role="alert"
            data-testid="composer-error"
            className="text-sm text-destructive"
          >
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

      <LiveCostPanel
        result={calcResult}
        loading={calcLoading}
        error={calcError}
      />

      <PrinterFileBrowser
        open={browsingPlateIdx !== null}
        onClose={() => setBrowsingPlateIdx(null)}
        onPicked={(plate) => {
          if (browsingPlateIdx !== null) applyDiscovered(browsingPlateIdx, plate);
          setBrowsingPlateIdx(null);
        }}
      />
    </section>
  );
}
