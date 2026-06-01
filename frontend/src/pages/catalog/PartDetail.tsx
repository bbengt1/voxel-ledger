/**
 * `/catalog/parts/:id` — view/edit a Part (assembly-line epic #267, Phase 1b).
 * Identity + print recipe + image (upload / replace / paste) + archive.
 * Cost shows "— (cost pending)" until the Phase 2 rollup populates it.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { EntityImage } from "@/components/catalog/EntityImage";
import { EntityPicker, type EntityOption } from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { formatCurrency, useCurrency } from "@/lib/currency";
import { useAuthStore } from "@/store/useAuthStore";

type PartResponse = components["schemas"]["PartResponse"];
type PrinterResponse = components["schemas"]["PrinterResponse"];
type MaterialResponse = components["schemas"]["MaterialResponse"];

const CAN_WRITE_ROLES = ["owner", "production", "sales"] as const;

interface MaterialRow {
  key: string;
  material: EntityOption | null;
  grams: string;
}
let _key = 0;
const nextKey = () => `m${++_key}`;

function parseIntSafe(s: string, fallback = 0): number {
  const n = Number.parseInt(s, 10);
  return Number.isFinite(n) ? n : fallback;
}

export function PartDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";
  const canWrite = role ? (CAN_WRITE_ROLES as readonly string[]).includes(role) : false;
  const currency = useCurrency();

  const [part, setPart] = useState<PartResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [printMinutes, setPrintMinutes] = useState("");
  const [setupMinutes, setSetupMinutes] = useState("0");
  const [partsPerRun, setPartsPerRun] = useState("1");
  const [materials, setMaterials] = useState<MaterialRow[]>([]);
  const [printerIds, setPrinterIds] = useState<string[]>([]);
  const [printers, setPrinters] = useState<PrinterResponse[]>([]);

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [imageKey, setImageKey] = useState(0);
  const [imageBusy, setImageBusy] = useState(false);

  const syncForm = useCallback(
    (p: PartResponse, materialsById: Record<string, MaterialResponse>) => {
      setName(p.name);
      setDescription(p.description ?? "");
      setPrintMinutes(String(p.print_minutes));
      setSetupMinutes(String(p.setup_minutes));
      setPartsPerRun(String(p.parts_per_run));
      const rows: MaterialRow[] = Object.entries(p.print_grams_by_material ?? {}).map(
        ([mid, grams]) => ({
          key: nextKey(),
          material: { id: mid, label: materialsById[mid]?.name ?? "Material" },
          grams: String(grams),
        }),
      );
      setMaterials(rows);
      setPrinterIds([...(p.assigned_printer_ids ?? [])]);
    },
    [],
  );

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    // Resolve material names + printers alongside the part.
    Promise.all([
      apiClient.get<PartResponse>(`/api/v1/parts/${id}`),
      api.get("/api/v1/materials", { params: { is_archived: "false" } }),
      api.get("/api/v1/printers", { params: { is_archived: "false" } }),
    ])
      .then(([partRes, matRes, prRes]) => {
        if (cancelled) return;
        const map: Record<string, MaterialResponse> = {};
        for (const m of matRes.data.items) map[m.id] = m;
        setPrinters(prRes.data.items);
        setPart(partRes.data);
        syncForm(partRes.data, map);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
          "Failed to load part.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, syncForm]);

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

  async function save() {
    if (!id) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const grams: Record<string, string> = {};
      for (const m of materials) {
        if (!m.material) continue;
        const g = Number.parseFloat(m.grams);
        if (!Number.isFinite(g) || g <= 0) continue;
        grams[m.material.id] = String(g);
      }
      const body: Record<string, unknown> = {
        name,
        description: description.trim() || null,
        print_minutes: parseIntSafe(printMinutes, 0),
        setup_minutes: parseIntSafe(setupMinutes, 0),
        parts_per_run: parseIntSafe(partsPerRun, 1),
        print_grams_by_material: grams,
        assigned_printer_ids: printerIds,
      };
      const res = await apiClient.patch<PartResponse>(`/api/v1/parts/${id}`, body);
      setPart(res.data);
      setSaveMsg("Saved.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        "Save failed.";
      setSaveMsg(typeof detail === "string" ? detail : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function onUploadImage(file: File) {
    if (!id) return;
    setImageBusy(true);
    setSaveMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await apiClient.post(`/api/v1/parts/${id}/image`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImageKey((k) => k + 1);
    } catch {
      setSaveMsg("Could not upload image.");
    } finally {
      setImageBusy(false);
    }
  }

  async function onRemoveImage() {
    if (!id) return;
    setImageBusy(true);
    try {
      await apiClient.delete(`/api/v1/parts/${id}/image`);
      setImageKey((k) => k + 1);
    } catch {
      setSaveMsg("Could not remove image.");
    } finally {
      setImageBusy(false);
    }
  }

  async function onPasteButton() {
    setSaveMsg(null);
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find((t) => t.startsWith("image/"));
        if (type) {
          const blob = await item.getType(type);
          const ext = type.split("/")[1] ?? "png";
          await onUploadImage(new File([blob], `pasted.${ext}`, { type }));
          return;
        }
      }
      setSaveMsg("No image found on the clipboard.");
    } catch {
      setSaveMsg(
        "Couldn't read the clipboard — copy an image, then click into this box and press Ctrl/Cmd+V.",
      );
    }
  }

  function onPasteImage(e: React.ClipboardEvent) {
    const file = Array.from(e.clipboardData.items)
      .find((it) => it.type.startsWith("image/"))
      ?.getAsFile();
    if (file) {
      e.preventDefault();
      void onUploadImage(file);
    }
  }

  async function setArchived(archived: boolean) {
    if (!id) return;
    try {
      const path = archived ? "archive" : "unarchive";
      const res = await apiClient.post<PartResponse>(`/api/v1/parts/${id}/${path}`);
      setPart(res.data);
    } catch {
      setSaveMsg("Could not change archive state.");
    }
  }

  if (loading) return <p>Loading…</p>;
  if (error || !part)
    return (
      <div role="alert" className="text-destructive">
        {error ?? "Part not found."}
      </div>
    );

  return (
    <section className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{part.name}</h1>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono text-xs">{part.sku}</span> ·{" "}
          {part.is_archived ? "Archived" : "Active"} ·{" "}
          <span data-testid="part-cost">
            Cost{" "}
            {part.unit_cost_cached
              ? formatCurrency(part.unit_cost_cached, currency)
              : "— (cost pending)"}
          </span>
        </p>
      </header>

      <section
        className="space-y-2 rounded-lg border border-border p-4"
        data-testid="part-image-section"
      >
        <h2 className="text-sm font-semibold">Image</h2>
        <div className="flex items-start gap-4">
          <EntityImage
            basePath={`/api/v1/parts/${part.id}`}
            size="full"
            refreshKey={imageKey}
            className="h-40 w-40 border border-border"
            alt={`${part.name} image`}
            testIdPrefix="part-image"
          />
          {canWrite ? (
            <div className="space-y-2 text-sm">
              <div
                role="button"
                tabIndex={0}
                onPaste={onPasteImage}
                className="cursor-text rounded border border-dashed border-input bg-muted/30 px-3 py-2 text-xs text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                data-testid="part-image-paste-zone"
              >
                Click here and press Ctrl/Cmd+V to paste an image
              </div>
              <label className="block">
                <span className="text-xs text-muted-foreground">
                  …or choose a file (uploading replaces the current image)
                </span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  disabled={imageBusy}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void onUploadImage(f);
                    e.target.value = "";
                  }}
                  data-testid="part-image-input"
                  className="mt-1 block text-sm"
                />
              </label>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={imageBusy}
                  onClick={() => void onPasteButton()}
                >
                  Paste from clipboard
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={imageBusy}
                  onClick={() => void onRemoveImage()}
                >
                  Remove image
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </section>

      {canWrite ? (
        <fieldset className="space-y-3" data-testid="part-edit-form">
          <legend className="text-sm font-medium">Profile</legend>
          <label className="block text-sm">
            Name
            <Input className="mt-1" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="block text-sm">
            Description
            <Input
              className="mt-1"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <div className="grid grid-cols-3 gap-3">
            <label className="block text-sm">
              Print min
              <Input
                type="number"
                min={0}
                className="mt-1"
                value={printMinutes}
                onChange={(e) => setPrintMinutes(e.target.value)}
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
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setMaterials((prev) => prev.filter((r) => r.key !== m.key))}
                >
                  ×
                </Button>
              </div>
            ))}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() =>
                  setMaterials((prev) => [...prev, { key: nextKey(), material: null, grams: "" }])
                }
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
                            checked ? prev.filter((pid) => pid !== pr.id) : [...prev, pr.id],
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

          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} data-testid="part-save-btn">
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button variant="outline" onClick={() => navigate("/catalog/parts")}>
              Back
            </Button>
          </div>
          {saveMsg ? (
            <p role="status" data-testid="part-save-msg" className="text-sm">
              {saveMsg}
            </p>
          ) : null}
        </fieldset>
      ) : null}

      {isOwner ? (
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Lifecycle</h2>
          <div className="flex gap-2">
            {part.is_archived ? (
              <Button onClick={() => void setArchived(false)} data-testid="part-unarchive-btn">
                Unarchive
              </Button>
            ) : (
              <Button
                variant="destructive"
                onClick={() => void setArchived(true)}
                data-testid="part-archive-btn"
              >
                Archive
              </Button>
            )}
          </div>
        </section>
      ) : null}
    </section>
  );
}
