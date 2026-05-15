/**
 * Discovery upload — sends a g-code sidecar (`.gcode.json` from
 * PrusaSlicer / Bambu Studio) to `POST /api/v1/jobs/discover` and exposes
 * the parsed fields so the parent can pre-fill a plate row.
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
          accept=".json,.gcode.json,application/json"
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
          {loading ? "Parsing…" : "Discover from g-code"}
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
