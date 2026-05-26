import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { usePlacesOfPurchase } from "@/lib/placesOfPurchase";

type SupplyResponse = components["schemas"]["SupplyResponse"];

export function SupplyCreatePage() {
  const navigate = useNavigate();
  const places = usePlacesOfPurchase();
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("each");
  const [unitCost, setUnitCost] = useState("");
  const [vendor, setVendor] = useState("");
  const [itemNumber, setItemNumber] = useState("");
  const [placeOfPurchase, setPlaceOfPurchase] = useState("");
  const [lowStockThreshold, setLowStockThreshold] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name,
        unit,
        unit_cost: unitCost,
      };
      if (vendor.trim()) body["vendor"] = vendor.trim();
      if (itemNumber.trim()) body["item_number"] = itemNumber.trim();
      if (placeOfPurchase.trim())
        body["place_of_purchase"] = placeOfPurchase.trim();
      if (lowStockThreshold.trim())
        body["low_stock_threshold"] = lowStockThreshold.trim();
      const res = await apiClient.post<SupplyResponse>(
        "/api/v1/supplies",
        body,
      );
      navigate(`/catalog/supplies/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create supply.";
      setError(typeof detail === "string" ? detail : "Could not create supply.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New supply</h1>
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
          Unit
          <Input
            className="mt-1"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          Unit cost
          <Input
            className="mt-1"
            inputMode="decimal"
            value={unitCost}
            onChange={(e) => setUnitCost(e.target.value)}
            required
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
            list="place-of-purchase-options"
            placeholder="Amazon, eBay, Home Depot, …"
            data-testid="place-of-purchase-input"
          />
          <datalist id="place-of-purchase-options">
            {places.map((p) => (
              <option key={p} value={p} />
            ))}
          </datalist>
        </label>
        <label className="block text-sm">
          Low-stock threshold (optional)
          <Input
            className="mt-1"
            inputMode="decimal"
            value={lowStockThreshold}
            onChange={(e) => setLowStockThreshold(e.target.value)}
          />
        </label>

        {error ? (
          <p role="alert" data-testid="create-error" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create supply"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/catalog/supplies")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
