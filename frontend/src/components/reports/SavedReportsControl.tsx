/**
 * Reusable Save / Load dropdown for any report page (Parity #237).
 *
 * Reads the current filter state (an opaque object) from the parent
 * and forwards selected presets back via ``onLoad``. The parent is
 * responsible for re-applying the filters — this control is pure
 * UI + a thin axios wrapper over ``/api/v1/saved-reports``.
 *
 * The component is per-user automatically (the backend scopes on
 * the JWT) — no extra plumbing needed.
 */
import { useCallback, useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type SavedReport = components["schemas"]["SavedReportRead"];

export interface SavedReportsControlProps {
  reportKind: string;
  currentFilters: Record<string, unknown>;
  onLoad: (filters: Record<string, unknown>) => void;
}

export function SavedReportsControl({
  reportKind,
  currentFilters,
  onLoad,
}: SavedReportsControlProps) {
  const [saved, setSaved] = useState<SavedReport[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await apiClient.get<SavedReport[]>(
        "/api/v1/saved-reports",
        { params: { report_kind: reportKind } },
      );
      setSaved(res.data);
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to load saved reports",
      );
    }
  }, [reportKind]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onSave() {
    if (!name.trim()) {
      setError("Name required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await apiClient.post("/api/v1/saved-reports", {
        name: name.trim(),
        report_kind: reportKind,
        filters: currentFilters,
      });
      setName("");
      await refresh();
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Save failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: string) {
    setBusy(true);
    setError(null);
    try {
      await apiClient.delete(`/api/v1/saved-reports/${id}`);
      await refresh();
    } catch (err) {
      setError(
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Delete failed",
      );
    } finally {
      setBusy(false);
    }
  }

  function handleLoadChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const id = e.target.value;
    if (!id) return;
    const row = saved.find((r) => r.id === id);
    if (row) onLoad(row.filters as Record<string, unknown>);
    // Reset selector so the same preset can be picked twice.
    e.target.value = "";
  }

  return (
    <div
      className="flex flex-wrap items-end gap-2"
      data-testid="saved-reports-control"
    >
      <label className="text-xs">
        Load saved
        <select
          className="mt-1 h-9 w-44 rounded-md border border-input bg-background px-2 text-sm"
          onChange={handleLoadChange}
          data-testid="saved-reports-select"
          defaultValue=""
        >
          <option value="">— pick a preset —</option>
          {saved.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </label>

      <label className="text-xs">
        Save current
        <div className="flex gap-1">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Preset name"
            className="w-40"
            data-testid="saved-reports-name"
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => void onSave()}
            disabled={busy || !name.trim()}
            data-testid="saved-reports-save"
          >
            Save
          </Button>
        </div>
      </label>

      {saved.length > 0 ? (
        <details className="text-xs">
          <summary
            className="cursor-pointer text-muted-foreground"
            data-testid="saved-reports-manage"
          >
            Manage ({saved.length})
          </summary>
          <ul className="mt-1 max-h-40 space-y-1 overflow-auto pr-2">
            {saved.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-2"
              >
                <span className="truncate">{r.name}</span>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void onDelete(r.id)}
                  data-testid={`saved-reports-delete-${r.id}`}
                >
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {error ? (
        <span className="text-xs text-red-600" data-testid="saved-reports-error">
          {error}
        </span>
      ) : null}
    </div>
  );
}
