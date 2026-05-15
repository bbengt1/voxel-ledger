import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type PrinterResponse = components["schemas"]["PrinterResponse"];

const TYPE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "prusa_mk4", label: "Prusa MK4" },
  { value: "prusa_mk3s", label: "Prusa MK3S" },
  { value: "bambu_x1c", label: "Bambu X1C" },
  { value: "bambu_a1", label: "Bambu A1" },
  { value: "voron_v2_4", label: "Voron 2.4" },
  { value: "other", label: "Other" },
];

export function PrinterCreatePage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [printerType, setPrinterType] = useState<string>("prusa_mk4");
  const [moonrakerUrl, setMoonrakerUrl] = useState("");
  const [moonrakerApiKey, setMoonrakerApiKey] = useState("");
  const [powerDrawWatts, setPowerDrawWatts] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name,
        slug,
        printer_type: printerType,
      };
      if (moonrakerUrl.trim()) body["moonraker_url"] = moonrakerUrl.trim();
      if (moonrakerApiKey.trim())
        body["moonraker_api_key"] = moonrakerApiKey.trim();
      if (powerDrawWatts.trim()) {
        const n = Number.parseInt(powerDrawWatts, 10);
        if (!Number.isNaN(n)) body["power_draw_watts"] = n;
      }
      if (notes.trim()) body["notes"] = notes.trim();

      const res = await apiClient.post<PrinterResponse>(
        "/api/v1/printers",
        body,
      );
      navigate(`/production/printers/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create printer.";
      setError(typeof detail === "string" ? detail : "Could not create printer.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New printer</h1>
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
          Slug
          <Input
            className="mt-1"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            maxLength={64}
          />
        </label>
        <label className="block text-sm">
          Type
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={printerType}
            onChange={(e) => setPrinterType(e.target.value)}
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Moonraker URL
          <Input
            className="mt-1"
            value={moonrakerUrl}
            onChange={(e) => setMoonrakerUrl(e.target.value)}
            placeholder="http://printer.local:7125"
          />
        </label>
        <label className="block text-sm">
          Moonraker API key
          <Input
            className="mt-1"
            type="password"
            value={moonrakerApiKey}
            onChange={(e) => setMoonrakerApiKey(e.target.value)}
            placeholder="(stored opaquely)"
          />
        </label>
        <label className="block text-sm">
          Power draw (W)
          <Input
            className="mt-1"
            type="number"
            min={0}
            max={10000}
            value={powerDrawWatts}
            onChange={(e) => setPowerDrawWatts(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Notes
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
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
            {submitting ? "Creating..." : "Create printer"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/production/printers")}
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
