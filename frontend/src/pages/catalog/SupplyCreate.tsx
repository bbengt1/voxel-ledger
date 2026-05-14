import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type SupplyResponse = components["schemas"]["SupplyResponse"];

export function SupplyCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("each");
  const [unitCost, setUnitCost] = useState("");
  const [vendor, setVendor] = useState("");
  const [onHand, setOnHand] = useState("0");

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
        on_hand: onHand || "0",
      };
      if (vendor.trim()) body["vendor"] = vendor.trim();
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
          Starting on-hand
          <Input
            className="mt-1"
            inputMode="decimal"
            value={onHand}
            onChange={(e) => setOnHand(e.target.value)}
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
