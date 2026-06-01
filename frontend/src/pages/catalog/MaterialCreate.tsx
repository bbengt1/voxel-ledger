import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useMaterialTypes } from "@/lib/materialTypes";

type MaterialResponse = components["schemas"]["MaterialResponse"];

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
  // Cost basis: price per spool drives cost-per-gram = price / spool weight.
  const [pricePerSpool, setPricePerSpool] = useState("");
  const materialTypes = useMaterialTypes();

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const totalGrams = useMemo(() => {
    const s = Number(spools);
    const w = Number(weightPerSpool);
    if (!Number.isFinite(s) || !Number.isFinite(w) || s <= 0 || w <= 0)
      return null;
    return s * w;
  }, [spools, weightPerSpool]);

  // Live cost-per-gram preview = price per spool ÷ spool weight. This is
  // exactly what the opening receipt establishes server-side, so the
  // operator sees the resulting cost/gram before saving.
  const costPerGram = useMemo(() => {
    const p = Number(pricePerSpool);
    const w = Number(weightPerSpool);
    if (!Number.isFinite(p) || !Number.isFinite(w) || p <= 0 || w <= 0)
      return null;
    return p / w;
  }, [pricePerSpool, weightPerSpool]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const spoolWeightNum = Number(weightPerSpool);
      if (!Number.isFinite(spoolWeightNum) || spoolWeightNum <= 0) {
        setError("Spool weight (g) is required and must be greater than zero.");
        setSubmitting(false);
        return;
      }
      const body: Record<string, unknown> = {
        name,
        material_type: materialType,
        spool_weight_grams: weightPerSpool,
      };
      if (brand.trim()) body["brand"] = brand.trim();
      if (color.trim()) body["color"] = color.trim();
      if (density.trim()) body["density_g_per_cm3"] = density.trim();
      const res = await apiClient.post<MaterialResponse>(
        "/api/v1/materials",
        body,
      );
      const materialId = res.data.id;

      // Optional initial-stock receipt as a spool-centric receipt. Only
      // fired when the operator entered a spool count (location is
      // resolved server-side from the default receiving setting).
      const spoolsNum = Number(spools);
      if (Number.isFinite(spoolsNum) && spoolsNum > 0) {
        const priceNum = Number(pricePerSpool);
        const priceStr =
          Number.isFinite(priceNum) && priceNum > 0
            ? String(priceNum)
            : "0";
        try {
          await apiClient.post(`/api/v1/materials/${materialId}/receipts`, {
            spools: Math.trunc(spoolsNum),
            extra_grams: "0",
            price_per_spool: priceStr,
            reference: "Initial stock",
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
        <label className="block text-sm">
          Spool weight (g)
          <Input
            className="mt-1"
            inputMode="decimal"
            value={weightPerSpool}
            onChange={(e) => setWeightPerSpool(e.target.value)}
            required
            data-testid="weight-per-spool-input"
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Every receipt is recorded as a number of spools at this weight.
          </span>
        </label>

        <fieldset className="rounded border border-border p-3">
          <legend className="px-1 text-xs uppercase text-muted-foreground">
            Initial stock (optional)
          </legend>
          <p className="text-xs text-muted-foreground">
            If you already have stock on hand, enter the spool count and the
            price per spool to post an opening receipt automatically. The
            price establishes the material's cost per gram
            (price ÷ spool weight).
          </p>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
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
              Price per spool ($)
              <Input
                className="mt-1"
                inputMode="decimal"
                value={pricePerSpool}
                onChange={(e) => setPricePerSpool(e.target.value)}
                data-testid="price-per-spool-input"
              />
            </label>
          </div>
          {totalGrams !== null ? (
            <p className="mt-2 text-xs" data-testid="total-grams-preview">
              <span className="text-muted-foreground">Total: </span>
              <span className="font-medium tabular-nums">
                {totalGrams.toFixed(2)} g
              </span>
            </p>
          ) : null}
          {costPerGram !== null ? (
            <p className="mt-1 text-xs" data-testid="cost-per-gram-preview">
              <span className="text-muted-foreground">Cost per gram: </span>
              <span className="font-medium tabular-nums">
                ${costPerGram.toFixed(4)}/g
              </span>
            </p>
          ) : null}
          {costPerGram !== null && totalGrams === null ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Enter a spool count to record stock at this price so the cost
              per gram is captured.
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
