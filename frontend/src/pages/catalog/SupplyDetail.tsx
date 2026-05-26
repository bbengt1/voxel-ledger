import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { OnHandSection } from "@/components/inventory/OnHandSection";
import { AttachmentsSection } from "@/components/platform/AttachmentsSection";
import { NotesSection } from "@/components/platform/NotesSection";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { usePlacesOfPurchase } from "@/lib/placesOfPurchase";
import { useAuthStore } from "@/store/useAuthStore";

type SupplyResponse = components["schemas"]["SupplyResponse"];

const CAN_WRITE_ROLES = ["owner", "production"] as const;

export function SupplyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const places = usePlacesOfPurchase();
  const [supply, setSupply] = useState<SupplyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [unit, setUnit] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [vendor, setVendor] = useState("");
  const [itemNumber, setItemNumber] = useState("");
  const [placeOfPurchase, setPlaceOfPurchase] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  function syncForm(s: SupplyResponse) {
    setName(s.name);
    setUnit(s.unit);
    setUnitCost(s.unit_cost);
    setVendor(s.vendor ?? "");
    setItemNumber(s.item_number ?? "");
    setPlaceOfPurchase(s.place_of_purchase ?? "");
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<SupplyResponse>(`/api/v1/supplies/${id}`)
      .then((res) => {
        if (cancelled) return;
        setSupply(res.data);
        syncForm(res.data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load supply.";
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
        unit,
        unit_cost: unitCost,
      };
      body["vendor"] = vendor.trim() || null;
      body["item_number"] = itemNumber.trim() || null;
      body["place_of_purchase"] = placeOfPurchase.trim() || null;
      const res = await apiClient.patch<SupplyResponse>(
        `/api/v1/supplies/${id}`,
        body,
      );
      setSupply(res.data);
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
      const res = await apiClient.post<SupplyResponse>(
        `/api/v1/supplies/${id}/archive`,
      );
      setSupply(res.data);
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
      const res = await apiClient.post<SupplyResponse>(
        `/api/v1/supplies/${id}/unarchive`,
      );
      setSupply(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not unarchive.";
      setSaveMsg(detail);
    }
  }

  if (loading) return <p>Loading…</p>;
  if (error || !supply)
    return (
      <div role="alert" className="text-destructive">
        {error ?? "Supply not found."}
      </div>
    );

  return (
    <section className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{supply.name}</h1>
        <p className="text-sm text-muted-foreground">
          {supply.is_archived ? "Archived" : "Active"} ·{" "}
          <span data-testid="unit-cost">
            {supply.unit_cost}/{supply.unit}
          </span>
        </p>
      </header>

      <OnHandSection
        entityKind="supply"
        entityId={supply.id}
        entityName={supply.name}
        totalOnHand={supply.total_on_hand}
        perLocationOnHand={supply.per_location_on_hand ?? null}
        unit={supply.unit}
        lowStockThreshold={supply.low_stock_threshold ?? null}
        onChanged={() => {
          if (!id) return;
          apiClient
            .get<SupplyResponse>(`/api/v1/supplies/${id}`)
            .then((res) => setSupply(res.data))
            .catch(() => {});
        }}
      />

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
            Unit
            <Input
              className="mt-1"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Unit cost
            <Input
              className="mt-1"
              inputMode="decimal"
              value={unitCost}
              onChange={(e) => setUnitCost(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Vendor
            <Input
              className="mt-1"
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Item number
            <Input
              className="mt-1"
              value={itemNumber}
              onChange={(e) => setItemNumber(e.target.value)}
              placeholder="Vendor SKU, ASIN, etc."
              data-testid="item-number-input"
            />
          </label>
          <label className="block text-sm">
            Place of purchase
            <Input
              className="mt-1"
              value={placeOfPurchase}
              onChange={(e) => setPlaceOfPurchase(e.target.value)}
              list="supply-place-of-purchase-options"
              data-testid="place-of-purchase-input"
            />
            <datalist id="supply-place-of-purchase-options">
              {places.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </label>
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} data-testid="save-btn">
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate("/catalog/supplies")}
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

      {isOwner ? (
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Lifecycle</h2>
          <div className="flex gap-2">
            {supply.is_archived ? (
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

      {/* Phase 2.6: notes + attachments */}
      {id ? (
        <>
          <NotesSection entityKind="supply" entityId={id} />
          <AttachmentsSection entityKind="supply" entityId={id} />
        </>
      ) : null}
    </section>
  );
}
