import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ProductResponse = components["schemas"]["ProductResponse"];

export function ProductCreatePage() {
  const navigate = useNavigate();
  const [sku, setSku] = useState("");
  const [upc, setUpc] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [weight, setWeight] = useState("");
  const [category, setCategory] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name,
        unit_price: unitPrice,
      };
      if (sku.trim()) body["sku"] = sku.trim();
      if (upc.trim()) body["upc"] = upc.trim();
      if (description.trim()) body["description"] = description.trim();
      if (weight.trim()) body["weight_grams"] = weight.trim();
      if (category.trim()) body["category"] = category.trim();
      const res = await apiClient.post<ProductResponse>(
        "/api/v1/products",
        body,
      );
      navigate(`/catalog/products/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create product.";
      setError(typeof detail === "string" ? detail : "Could not create product.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New product</h1>
      <form className="mt-6 space-y-3" onSubmit={onSubmit}>
        <label className="block text-sm">
          SKU
          <Input
            className="mt-1"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder="auto-generated"
            data-testid="sku-input"
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Leave blank to auto-generate as PROD-YYYY-NNNN.
          </span>
        </label>
        <label className="block text-sm">
          UPC
          <Input
            className="mt-1"
            value={upc}
            onChange={(e) => setUpc(e.target.value)}
          />
        </label>
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
          Description
          <Input
            className="mt-1"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Unit price
          <Input
            className="mt-1"
            inputMode="decimal"
            value={unitPrice}
            onChange={(e) => setUnitPrice(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          Weight (g)
          <Input
            className="mt-1"
            inputMode="decimal"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Category
          <Input
            className="mt-1"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </label>

        {error ? (
          <p
            role="alert"
            data-testid="create-error"
            className="text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create product"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/catalog/products")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
