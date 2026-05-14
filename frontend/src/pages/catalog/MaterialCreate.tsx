import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type MaterialResponse = components["schemas"]["MaterialResponse"];

export function MaterialCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [materialType, setMaterialType] = useState("PLA");
  const [color, setColor] = useState("");
  const [density, setDensity] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      navigate(`/catalog/materials/${res.data.id}`);
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
          <Input
            className="mt-1"
            value={materialType}
            onChange={(e) => setMaterialType(e.target.value)}
            required
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
            onClick={() => navigate("/catalog/materials")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
