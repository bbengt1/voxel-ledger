/**
 * Discovery upload — POSTs a slicer artifact to `/api/v1/jobs/discover`
 * and surfaces the parsed plate fields. Accepts:
 *
 *   - ``.gcode.json`` sidecars (PrusaSlicer / Bambu Studio)
 *   - ``.3mf`` sliced archives (Bambu, OrcaSlicer, PrusaSlicer)
 *
 * The backend detects format from the file bytes (zip magic vs JSON),
 * so the same endpoint handles both.
 */
import { useRef, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type DiscoveredPlate = components["schemas"]["DiscoveredPlateResponse"];

interface Props {
  onDiscovered: (plate: DiscoveredPlate) => void;
  /** Test/diagnostic id suffix. */
  "data-testid"?: string;
}

export function DiscoveryUpload({ onDiscovered, "data-testid": testId }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await apiClient.post<DiscoveredPlate>(
        "/api/v1/jobs/discover",
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      onDiscovered(res.data);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "Could not parse sidecar — check the file format.",
      );
    } finally {
      setLoading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept=".json,.gcode.json,application/json,.3mf,model/3mf,application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
          data-testid={testId ? `${testId}-input` : "discovery-file-input"}
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleFile(f);
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => inputRef.current?.click()}
          data-testid={testId ?? "discovery-trigger"}
        >
          {loading ? "Parsing…" : "Import 3MF / g-code"}
        </Button>
      </div>
      {error ? (
        <p
          role="alert"
          className="text-xs text-destructive"
          data-testid={testId ? `${testId}-error` : "discovery-error"}
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
