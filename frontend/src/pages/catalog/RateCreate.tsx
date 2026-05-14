import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type RateResponse = components["schemas"]["RateResponse"];
type RateKind = RateResponse["kind"];

export function RateCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<RateKind>("labor");
  const [value, setValue] = useState("");
  const [printerId, setPrinterId] = useState("");
  const [makeDefault, setMakeDefault] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name,
        kind,
        value,
        is_default_for_kind: makeDefault,
      };
      if (printerId.trim()) body["applies_to_printer_id"] = printerId.trim();
      const res = await apiClient.post<RateResponse>("/api/v1/rates", body);
      navigate(`/catalog/rates/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create rate.";
      setError(typeof detail === "string" ? detail : "Could not create rate.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New rate</h1>
      <form className="mt-6 space-y-3" onSubmit={onSubmit}>
        <label className="block text-sm">
          Kind
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={kind}
            onChange={(e) => setKind(e.target.value as RateKind)}
          >
            <option value="labor">Labor (per hour)</option>
            <option value="machine">Machine (per hour)</option>
            <option value="overhead">Overhead (decimal %)</option>
          </select>
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
          Value
          <Input
            className="mt-1"
            inputMode="decimal"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </label>
        {kind === "machine" ? (
          <label className="block text-sm">
            Applies to printer ID (optional)
            <Input
              className="mt-1"
              placeholder="(Phase 5 will replace this with a dropdown)"
              value={printerId}
              onChange={(e) => setPrinterId(e.target.value)}
            />
          </label>
        ) : null}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={makeDefault}
            onChange={(e) => setMakeDefault(e.target.checked)}
          />
          Make this the default for this kind
        </label>

        {error ? (
          <p role="alert" data-testid="create-error" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create rate"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/catalog/rates")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
