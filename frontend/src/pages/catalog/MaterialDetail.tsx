import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { ReceiptModal } from "@/components/catalog/ReceiptModal";
import { AttachmentsSection } from "@/components/platform/AttachmentsSection";
import { NotesSection } from "@/components/platform/NotesSection";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type MaterialDetailResponse =
  components["schemas"]["MaterialDetailResponse"];
type MaterialResponse = components["schemas"]["MaterialResponse"];
type MaterialReceiptResponse =
  components["schemas"]["MaterialReceiptResponse"];

const CAN_WRITE_ROLES = ["owner", "production"] as const;

export function MaterialDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [material, setMaterial] = useState<MaterialDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [materialType, setMaterialType] = useState("");
  const [color, setColor] = useState("");
  const [density, setDensity] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [receiptOpen, setReceiptOpen] = useState(false);

  function syncFormFromMaterial(m: MaterialResponse) {
    setName(m.name);
    setBrand(m.brand ?? "");
    setMaterialType(m.material_type);
    setColor(m.color ?? "");
    setDensity(m.density_g_per_cm3 ?? "");
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<MaterialDetailResponse>(`/api/v1/materials/${id}`)
      .then((res) => {
        if (cancelled) return;
        setMaterial(res.data);
        syncFormFromMaterial(res.data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load material.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function save() {
    if (!id) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const body: Record<string, unknown> = {
        name,
        material_type: materialType,
      };
      body["brand"] = brand.trim() || null;
      body["color"] = color.trim() || null;
      body["density_g_per_cm3"] = density.trim() || null;
      const res = await apiClient.patch<MaterialResponse>(
        `/api/v1/materials/${id}`,
        body,
      );
      setMaterial((m) =>
        m
          ? {
              ...m,
              ...res.data,
            }
          : m,
      );
      setSaveMsg("Saved.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Save failed.";
      setSaveMsg(typeof detail === "string" ? detail : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function doArchive() {
    if (!id) return;
    try {
      const res = await apiClient.post<MaterialResponse>(
        `/api/v1/materials/${id}/archive`,
      );
      setMaterial((m) => (m ? { ...m, ...res.data } : m));
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not archive.";
      setSaveMsg(detail);
    }
  }

  async function doUnarchive() {
    if (!id) return;
    try {
      const res = await apiClient.post<MaterialResponse>(
        `/api/v1/materials/${id}/unarchive`,
      );
      setMaterial((m) => (m ? { ...m, ...res.data } : m));
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not unarchive.";
      setSaveMsg(detail);
    }
  }

  function onReceiptRecorded(updated: MaterialResponse) {
    // After a receipt the cost + on-hand caches change. Refetch the
    // detail page so the receipt list updates too.
    if (!id) return;
    setMaterial((m) => (m ? { ...m, ...updated } : m));
    apiClient
      .get<MaterialDetailResponse>(`/api/v1/materials/${id}`)
      .then((res) => setMaterial(res.data))
      .catch(() => {
        // non-fatal: the cost is already correct from the POST response
      });
  }

  if (loading) return <p>Loading…</p>;
  if (error || !material)
    return (
      <div role="alert" className="text-destructive">
        {error ?? "Material not found."}
      </div>
    );

  return (
    <section className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{material.name}</h1>
        <p className="text-sm text-muted-foreground">
          {material.is_archived ? "Archived" : "Active"} ·{" "}
          <span data-testid="cost-per-gram">
            Cost {material.current_cost_per_gram}/g
          </span>{" "}
          ·{" "}
          <span data-testid="on-hand">
            {material.total_on_hand} g on hand
          </span>
        </p>
        {material.per_location_on_hand &&
        Object.keys(material.per_location_on_hand).length > 0 ? (
          <p
            className="mt-1 text-xs text-muted-foreground"
            data-testid="per-location-on-hand"
          >
            {Object.entries(material.per_location_on_hand)
              .map(([loc, qty]) => `${loc.slice(0, 8)}…: ${qty}g`)
              .join(" · ")}
          </p>
        ) : null}
      </header>

      {canWrite ? (
        <fieldset className="space-y-3" data-testid="edit-form">
          <legend className="text-sm font-medium">Profile</legend>
          <label className="block text-sm">
            Name
            <Input
              className="mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Brand
            <Input
              className="mt-1"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Material type
            <Input
              className="mt-1"
              value={materialType}
              onChange={(e) => setMaterialType(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Color
            <Input
              className="mt-1"
              value={color}
              onChange={(e) => setColor(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Density (g/cm³)
            <Input
              className="mt-1"
              inputMode="decimal"
              value={density}
              onChange={(e) => setDensity(e.target.value)}
            />
          </label>
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} data-testid="save-btn">
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate("/catalog/materials")}
            >
              Back
            </Button>
          </div>
          {saveMsg ? (
            <p role="status" data-testid="save-msg" className="text-sm">
              {saveMsg}
            </p>
          ) : null}
        </fieldset>
      ) : null}

      {canWrite ? (
        <section className="space-y-3 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Inventory</h2>
          <Button
            onClick={() => setReceiptOpen(true)}
            data-testid="open-receipt-modal"
          >
            Record receipt
          </Button>
        </section>
      ) : null}

      <section className="space-y-2 border-t border-border pt-4">
        <h2 className="text-sm font-semibold">Recent receipts</h2>
        {material.recent_receipts && material.recent_receipts.length > 0 ? (
          <table className="w-full table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-2">Received</th>
                <th className="py-2 pr-2">Grams</th>
                <th className="py-2 pr-2">Total</th>
                <th className="py-2 pr-2">Unit cost</th>
                <th className="py-2 pr-2">Vendor</th>
              </tr>
            </thead>
            <tbody>
              {material.recent_receipts.map((r: MaterialReceiptResponse) => (
                <tr key={r.id} className="border-b border-border/50">
                  <td className="py-2 pr-2">
                    {new Date(r.received_at).toLocaleString()}
                  </td>
                  <td className="py-2 pr-2">{r.grams}</td>
                  <td className="py-2 pr-2">{r.total_cost}</td>
                  <td className="py-2 pr-2">{r.unit_cost_at_receipt}</td>
                  <td className="py-2 pr-2">{r.vendor ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted-foreground">No receipts yet.</p>
        )}
      </section>

      {isOwner ? (
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Lifecycle</h2>
          <div className="flex gap-2">
            {material.is_archived ? (
              <Button onClick={doUnarchive} data-testid="unarchive-btn">
                Unarchive
              </Button>
            ) : (
              <Button
                variant="destructive"
                onClick={doArchive}
                data-testid="archive-btn"
              >
                Archive
              </Button>
            )}
          </div>
        </section>
      ) : null}

      <ReceiptModal
        open={receiptOpen}
        materialId={id ?? ""}
        onClose={() => setReceiptOpen(false)}
        onRecorded={onReceiptRecorded}
      />

      {/* Phase 2.6: notes + attachments */}
      {id ? (
        <>
          <NotesSection entityKind="material" entityId={id} />
          <AttachmentsSection entityKind="material" entityId={id} />
        </>
      ) : null}
    </section>
  );
}
