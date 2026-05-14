import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

const KIND_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "workshop", label: "Workshop" },
  { value: "finished_goods", label: "Finished goods" },
  { value: "staging", label: "Staging" },
  { value: "customer_pickup", label: "Customer pickup" },
  { value: "consignment", label: "Consignment" },
  { value: "virtual", label: "Virtual" },
];

export function LocationCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [kind, setKind] = useState<string>("workshop");
  const [description, setDescription] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { name, code, kind };
      if (description.trim()) body["description"] = description.trim();
      const res = await apiClient.post<InventoryLocationResponse>(
        "/api/v1/inventory/locations",
        body,
      );
      navigate(`/inventory/locations/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create location.";
      setError(typeof detail === "string" ? detail : "Could not create location.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New inventory location</h1>
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
          Code
          <Input
            className="mt-1"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            maxLength={32}
          />
        </label>
        <label className="block text-sm">
          Kind
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Description
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
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
            {submitting ? "Creating…" : "Create location"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/inventory/locations")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
