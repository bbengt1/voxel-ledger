import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useMaterialTypes } from "@/lib/materialTypes";

type MaterialResponse = components["schemas"]["MaterialResponse"];
type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

export function MaterialCreatePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("return_to");
  const [name, setName] = useState(searchParams.get("name") ?? "");
  const [brand, setBrand] = useState("");
  const [materialType, setMaterialType] = useState(
    searchParams.get("material_type") ?? "PLA",
  );
  const [materialTypeCustom, setMaterialTypeCustom] = useState(false);
  const [color, setColor] = useState("");
  const [density, setDensity] = useState("");

  // Initial-stock helper: total grams = spools × weight/spool.
  const [spools, setSpools] = useState("");
  const [weightPerSpool, setWeightPerSpool] = useState("");
  const [stockLocationId, setStockLocationId] = useState("");
  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);

  const materialTypes = useMaterialTypes();

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ items: InventoryLocationResponse[] }>(
        "/api/v1/inventory/locations",
        { params: { is_archived: "false" } },
      )
      .then((res) => {
        if (cancelled) return;
        setLocations(res.data.items);
      })
      .catch(() => {
        if (!cancelled) setLocations([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const totalGrams = useMemo(() => {
    const s = Number(spools);
    const w = Number(weightPerSpool);
    if (!Number.isFinite(s) || !Number.isFinite(w) || s <= 0 || w <= 0)
      return null;
    return s * w;
  }, [spools, weightPerSpool]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name,
        material_type: materialType,
      };
      if (brand.trim()) body["brand"] = brand.trim();
      if (color.trim()) body["color"] = color.trim();
      if (density.trim()) body["density_g_per_cm3"] = density.trim();
      const res = await apiClient.post<MaterialResponse>(
        "/api/v1/materials",
        body,
      );
      const materialId = res.data.id;

      // Optional initial-stock receipt. Only fired when the operator
      // entered spools + weight/spool + location. A failure here doesn't
      // unwind the material — we navigate anyway and show the error so
      // they can record the receipt manually from the detail page.
      if (totalGrams !== null && stockLocationId) {
        try {
          await apiClient.post("/api/v1/inventory/transactions", {
            kind: "receipt",
            entity_kind: "material",
            entity_id: materialId,
            location_id: stockLocationId,
            quantity: totalGrams.toString(),
            reason: `Initial stock: ${spools} spool(s) × ${weightPerSpool} g`,
          });
        } catch (recvErr: unknown) {
          const detail =
            (recvErr as { response?: { data?: { detail?: string } } }).response
              ?.data?.detail ?? "Material created, but initial stock failed.";
          setError(
            typeof detail === "string"
              ? `Material created, but initial stock failed: ${detail}`
              : "Material created, but initial stock failed.",
          );
        }
      }

      if (returnTo === "job_composer") {
        const params = new URLSearchParams();
        params.set("restored", "1");
        params.set("material_id", materialId);
        params.set("material_label", res.data.name);
        navigate(`/production/jobs/new?${params.toString()}`);
        return;
      }
      navigate(`/catalog/materials/${materialId}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create material.";
      setError(typeof detail === "string" ? detail : "Could not create material.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New material</h1>
      <form className="mt-6 space-y-3" onSubmit={onSubmit}>
        <label className="block text-sm">
          Name
          <Input
            className="mt-1"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
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
          {materialTypeCustom ? (
            <div className="mt-1 flex gap-2">
              <Input
                value={materialType}
                onChange={(e) => setMaterialType(e.target.value)}
                placeholder="Custom material type"
                required
                data-testid="material-type-input"
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setMaterialTypeCustom(false);
                  setMaterialType("PLA");
                }}
              >
                Pick from list
              </Button>
            </div>
          ) : (
            <select
              className="mt-1 block w-full rounded border border-input bg-background px-2 py-1 text-sm"
              value={materialType}
              onChange={(e) => {
                if (e.target.value === "__custom__") {
                  setMaterialTypeCustom(true);
                  setMaterialType("");
                } else {
                  setMaterialType(e.target.value);
                }
              }}
              required
              data-testid="material-type-select"
            >
              {materialTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
              <option value="__custom__">Other…</option>
            </select>
          )}
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

        <fieldset className="rounded border border-border p-3">
          <legend className="px-1 text-xs uppercase text-muted-foreground">
            Initial stock (optional)
          </legend>
          <p className="text-xs text-muted-foreground">
            If you have stock on hand, enter spool counts to post an opening
            receipt automatically.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Number of spools
              <Input
                className="mt-1"
                inputMode="decimal"
                value={spools}
                onChange={(e) => setSpools(e.target.value)}
                data-testid="spools-input"
              />
            </label>
            <label className="block text-sm">
              Weight per spool (g)
              <Input
                className="mt-1"
                inputMode="decimal"
                value={weightPerSpool}
                onChange={(e) => setWeightPerSpool(e.target.value)}
                data-testid="weight-per-spool-input"
              />
            </label>
          </div>
          <label className="mt-3 block text-sm">
            Receiving location
            <select
              className="mt-1 block w-full rounded border border-input bg-background px-2 py-1 text-sm"
              value={stockLocationId}
              onChange={(e) => setStockLocationId(e.target.value)}
              data-testid="stock-location"
            >
              <option value="">Select a location…</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          {totalGrams !== null ? (
            <p className="mt-2 text-xs" data-testid="total-grams-preview">
              <span className="text-muted-foreground">Total: </span>
              <span className="font-medium tabular-nums">{totalGrams} g</span>
              {!stockLocationId ? (
                <span className="text-muted-foreground">
                  {" "}
                  · pick a location to record on save
                </span>
              ) : null}
            </p>
          ) : null}
        </fieldset>

        {error ? (
          <p role="alert" data-testid="create-error" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create material"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              navigate(
                returnTo === "job_composer"
                  ? "/production/jobs/new?restored=1"
                  : "/catalog/materials",
              )
            }
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
